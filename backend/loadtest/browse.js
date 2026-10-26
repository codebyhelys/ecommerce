// Navegação anônima: o grosso do tráfego de uma loja (listagem, filtro, busca e detalhe).
import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE, CATEGORIES, rand, slug, word } from './lib.js';

const STAGES = (__ENV.STAGES || '20:30s,100:1m,300:1m,600:1m,0:20s')
  .split(',')
  .map((s) => ({ target: Number(s.split(':')[0]), duration: s.split(':')[1] }));

export const options = {
  stages: STAGES,
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500'],
    // um limite por tipo de requisição só para o k6 detalhá-las no relatório
    'http_req_duration{name:listagem}': ['p(95)<500'],
    'http_req_duration{name:categoria}': ['p(95)<500'],
    'http_req_duration{name:busca}': ['p(95)<500'],
    'http_req_duration{name:faixa-de-preco}': ['p(95)<500'],
    'http_req_duration{name:detalhe}': ['p(95)<500'],
  },
};

export default function () {
  const pick = Math.random();
  let res;
  if (pick < 0.4) {
    res = http.get(`${BASE}/products/?page=${1 + rand(40)}`, { tags: { name: 'listagem' } });
  } else if (pick < 0.6) {
    res = http.get(`${BASE}/products/?category=categoria-${1 + rand(CATEGORIES)}`, { tags: { name: 'categoria' } });
  } else if (pick < 0.75) {
    res = http.get(`${BASE}/products/?search=${encodeURIComponent(word())}`, { tags: { name: 'busca' } });
  } else if (pick < 0.85) {
    res = http.get(`${BASE}/products/?min_price=50&max_price=200&ordering=price`, { tags: { name: 'faixa-de-preco' } });
  } else {
    res = http.get(`${BASE}/products/${slug()}/`, { tags: { name: 'detalhe' } });
  }
  check(res, { 'status 200': (r) => r.status === 200 });
  sleep(Math.random() * 2);
}
