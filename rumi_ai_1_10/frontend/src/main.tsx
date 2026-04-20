import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import { bootstrapApiTokenFromLocation } from './lib/api.ts';
import './index.css';

bootstrapApiTokenFromLocation();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
