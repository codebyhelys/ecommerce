// Compra completa de um usuário logado: carrinho -> pedido -> pagamento.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE, SHIPPING, authHeaders, rand, slug } from './lib.js';

const STAGES = (__ENV.STAGES || '10:30s,50:1m,100:1m,200:1m,0:20s')
  .split(',')
  .map((s) => ({ target: Number(s.split(':')[0]), duration: s.split(':')[1] }));

export const options = {
  stages: STAGES,
  thresholds: {
    http_req_failed: ['rate<0.01'],
    'http_req_duration{name:pedido}': ['p(95)<1500'],
  },
};

export default function () {
  const params = authHeaders(__VU);

  http.get(`${BASE}/cart/`, { ...params, tags: { name: 'carrinho' } });

  for (let i = 0; i < 1 + rand(3); i++) {
    const add = http.post(`${BASE}/cart/items/`, JSON.stringify({ product: slug(), quantity: 1 + rand(2) }), {
      ...params,
      tags: { name: 'adicionar-item' },
    });
    check(add, { 'item adicionado': (r) => r.status === 201 });
  }

  const order = http.post(`${BASE}/orders/`, JSON.stringify(SHIPPING), { ...params, tags: { name: 'pedido' } });
  if (!check(order, { 'pedido criado': (r) => r.status === 201 })) return;

  const pay = http.post(`${BASE}/payments/`, JSON.stringify({ order: order.json('id'), method: 'pix' }), {
    ...params,
    tags: { name: 'pagamento' },
  });
  check(pay, { 'pagamento iniciado': (r) => r.status === 201 });
  sleep(1 + Math.random() * 2);
}
