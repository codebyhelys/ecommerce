// Contenção de estoque: todos os usuários compram o MESMO produto ao mesmo tempo.
//   PRODUCT=produto-quente   (estoque enorme: mede o custo da trava de linha)
//   PRODUCT=produto-limitado (300 unidades: prova que nunca se vende a mais; veja loadtest/README.md)
import http from 'k6/http';
import { check } from 'k6';
import { BASE, SHIPPING, authHeaders } from './lib.js';

const PRODUCT = __ENV.PRODUCT || 'produto-quente';

export const options = {
  scenarios: {
    rush: {
      executor: 'ramping-arrival-rate',
      startRate: 10,
      timeUnit: '1s',
      preAllocatedVUs: 200,
      maxVUs: 400,
      stages: [
        { target: 50, duration: '30s' },
        { target: 150, duration: '1m' },
        { target: 0, duration: '10s' },
      ],
    },
  },
};

export default function () {
  const params = authHeaders(__VU);
  http.post(`${BASE}/cart/items/`, JSON.stringify({ product: PRODUCT, quantity: 1 }), params);
  const order = http.post(`${BASE}/orders/`, JSON.stringify(SHIPPING), { ...params, tags: { name: 'pedido' } });
  // 201 = comprou; 409/400 = sem estoque (esperado no produto limitado); qualquer outra coisa é problema
  check(order, { 'resposta esperada': (r) => [201, 400, 409].includes(r.status) });
}
