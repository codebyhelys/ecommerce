// Funções e dados compartilhados pelos cenários.
import { SharedArray } from 'k6/data';

export const BASE = __ENV.BASE_URL || 'http://load-web:8000/api';
export const PRODUCTS = 5000; // produto-00001 .. produto-05000 (veja seed.py)
export const CATEGORIES = 20;

// um token por usuário de teste; cada VU usa o seu, para não disputar o carrinho do vizinho
export const tokens = new SharedArray('tokens', () => JSON.parse(open('./tokens.json')));

const WORDS = ['Camiseta', 'Calça', 'Jaqueta', 'Bermuda', 'Moletom', 'Boné', 'Meia', 'Tênis', 'Mochila', 'Relógio'];

export const SHIPPING = {
  shipping_name: 'Teste de Carga',
  shipping_zip_code: '01310-100',
  shipping_street: 'Avenida Paulista',
  shipping_number: '1000',
  shipping_complement: '',
  shipping_district: 'Bela Vista',
  shipping_city: 'São Paulo',
  shipping_state: 'SP',
};

export const rand = (n) => Math.floor(Math.random() * n);
export const word = () => WORDS[rand(WORDS.length)];
export const slug = () => `produto-${String(1 + rand(PRODUCTS)).padStart(5, '0')}`;

export function authHeaders(vu) {
  return {
    headers: {
      Authorization: `Token ${tokens[(vu - 1) % tokens.length]}`,
      'Content-Type': 'application/json',
    },
  };
}
