import App from './App.svelte';
import './global.css';

// Configure axios for better error handling
import axios from 'axios';
axios.interceptors.response.use(
  response => response,
  error => {
    console.error('API Error:', error);
    return Promise.reject(error);
  }
);

const app = new App({
  target: document.getElementById('app'),
});

export default app;
