import { mount } from 'svelte';
import App from './App.svelte';
import { installRelayTheme } from './theme';
import './styles.css';

installRelayTheme();
mount(App, { target: document.getElementById('design-app')! });
