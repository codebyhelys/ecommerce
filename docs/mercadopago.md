# Integração com o Mercado Pago (plano)

Estado: **não implementada**. O núcleo de pagamentos (`payments/`) já é independente de provedor; falta o
adaptador. Este documento lista o que a documentação oficial confirma, o que ainda precisa ser validado
no sandbox e o trabalho necessário. Não escreva o adaptador "às cegas": valide cada ponto marcado como
**[validar]** com credenciais de teste.

Fontes: [Webhooks](https://www.mercadopago.com.br/developers/pt/docs/checkout-pro/additional-content/notifications/webhooks)
e [Pix](https://www.mercadopago.com.br/developers/pt/docs/checkout-api-payments/integration-configuration/integrate-pix).

## O que a documentação confirma

**Criar o pagamento Pix** — `POST https://api.mercadopago.com/v1/payments`

- Cabeçalhos: `Authorization: Bearer <access token>`, `Content-Type: application/json` e
  **`X-Idempotency-Key`** (obrigatório; use um valor estável por pagamento nosso, ex.: `payment-<id>`).
- Obrigatórios no corpo: `transaction_amount`, `payment_method_id: "pix"`, `payer.email` e
  **`payer.identification` (tipo e número do documento, ex.: CPF)**.
- `date_of_expiration`: validade do Pix. Padrão **24 h**; aceita de **30 minutos a 30 dias**.
- Resposta: `id`, `status`, `status_detail` e, em `point_of_interaction.transaction_data`, os campos
  `qr_code` (copia-e-cola), `qr_code_base64` (imagem) e `ticket_url`.

**Webhook de pagamento**

- `POST` com JSON: `id` (id da notificação), `type`, `action`, `live_mode`, `user_id`, `api_version`,
  `date_created` e `data.id` (id do **pagamento**, não o status).
- O servidor deve responder **200 ou 201 em até 22 s**. Sem confirmação, o Mercado Pago reenvia a cada 15 min.
- A notificação não traz o status: é preciso consultar `GET /v1/payments/<id>`.
- Cabeçalho `x-signature: ts=<timestamp>,v1=<hash>`; a chave é a "assinatura secreta" da aplicação
  (painel de desenvolvedores, Webhooks).
- Notificações de QR Code (presencial) não têm `x-signature`; não é o nosso caso.

## O que NÃO estava nas páginas lidas — **[validar]** no sandbox

- Template exato da assinatura. Outras páginas indicam `id:<data.id>;request-id:<x-request-id>;ts:<ts>;`
  com HMAC-SHA256 em hexadecimal, mas a documentação é inconsistente entre páginas.
- Se `data.id` da assinatura vem da **query string** (`?data.id=...`) ou do corpo. Os SDKs leem da query.
- Se `external_reference` e `notification_url` são aceitos na criação do Pix (usaríamos `external_reference`
  com o id do nosso `Payment`, para casar o evento mesmo antes de gravarmos a referência do provedor).
- Lista completa de `status` (mapeamento provisório: `approved` → aprovado; `pending`, `in_process`,
  `authorized` → pendente; `rejected` → recusado; `cancelled`, `expired` → cancelado; `refunded`,
  `charged_back` → ainda não modelados).

## O que precisa mudar no código

1. **Assinatura do adaptador.** `parse_webhook(headers, body)` precisa também da **query string** e do
   `x-request-id` (hoje só recebe cabeçalhos e corpo). Ajustar `handle_webhook` e `WebhookView`.
2. **O adaptador consulta a API.** Depois de validar a assinatura, chama `GET /v1/payments/<data.id>` para
   obter status, valor e `external_reference`, e então devolve o `GatewayEvent`. Use timeout curto (10 s) e,
   se a consulta falhar, responda **5xx** para o Mercado Pago reenviar (hoje só existe 400 para webhook inválido).
3. **Idempotência do evento.** Usar o `id` da notificação como `event_id` (reenvios trazem o mesmo `id`).
4. **CPF do pagador.** O Pix exige documento. Receber no `POST /api/payments/` (ex.: `payer_document`) e
   repassar ao provedor **sem gravar no banco** (dado pessoal; LGPD). `payer.email` vem do usuário logado.
5. **Validade do Pix.** Enviar `date_of_expiration = agora + PAYMENT_WINDOW_MINUTES` (padrão 30, que é o
   mínimo aceito) para ficar alinhado com a expiração dos pedidos (`expire_pending_orders`).
6. **URL pública.** `notification_url` precisa ser acessível pela internet (em desenvolvimento, um túnel como
   ngrok). Nova variável `PUBLIC_BASE_URL`.
7. **Variáveis novas:** `MERCADOPAGO_ACCESS_TOKEN` e `MERCADOPAGO_WEBHOOK_SECRET` (somente no `.env`, nunca no git).
8. **Registro.** Incluir `"mercadopago"` em `GATEWAYS` (`payments/gateways.py`) e usar
   `PAYMENT_GATEWAY=mercadopago`.
9. **Estorno.** `needs_refund` só sinaliza. O estorno real (`POST /v1/payments/<id>/refunds`) é uma etapa à parte.

## Roteiro de validação no sandbox

1. Criar a aplicação no painel de desenvolvedores e copiar o **access token de teste** e a **assinatura secreta**.
2. Subir um túnel público para o `runserver` e cadastrar `https://<túnel>/api/payments/webhooks/mercadopago/`.
3. Criar um Pix de teste e confirmar os campos da resposta (`qr_code`, `ticket_url`).
4. Simular o pagamento e conferir: assinatura válida, evento processado, pedido `paid`.
5. Reenviar a mesma notificação e confirmar `duplicate`; alterar um byte do corpo e confirmar 400.
6. Pagar depois de cancelar o pedido e confirmar `needs_refund`.
