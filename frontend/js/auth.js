/**
 * Auth Module for App LTI
 */

const Auth = {
  TOKEN_KEY: 'app_lti_token',
  USER_KEY: 'app_lti_user',

  getToken() {
    return localStorage.getItem(this.TOKEN_KEY);
  },

  getUser() {
    const raw = localStorage.getItem(this.USER_KEY);
    try {
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  },

  isAuthenticated() {
    return !!this.getToken();
  },

  async login(username, password) {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Error al iniciar sesión' }));
      throw new Error(err.detail || 'Credenciales inválidas');
    }

    const data = await response.json();
    localStorage.setItem(this.TOKEN_KEY, data.access_token);
    localStorage.setItem(this.USER_KEY, JSON.stringify(data.user));
    return data.user;
  },

  logout() {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
    window.location.reload();
  },

  async fetchWithAuth(url, options = {}) {
    const token = this.getToken();
    const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;

    let headers = {};
    if (typeof Headers !== 'undefined' && options.headers instanceof Headers) {
      options.headers.forEach((val, key) => {
        headers[key] = val;
      });
    } else if (options.headers) {
      headers = { ...options.headers };
    }

    if (!isFormData && !Object.keys(headers).some(k => k.toLowerCase() === 'content-type')) {
      headers['Content-Type'] = 'application/json';
    }

    // Si es FormData, eliminar cualquier variante de Content-Type (Content-Type, content-type)
    // para permitir que el navegador genere automáticamente 'multipart/form-data; boundary=...'
    if (isFormData) {
      delete headers['Content-Type'];
      Object.keys(headers).forEach(k => {
        if (k.toLowerCase() === 'content-type') {
          if (!headers[k] || !String(headers[k]).includes('boundary=')) {
            delete headers[k];
          }
        }
      });
    }

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(url, { ...options, headers });

    if (response.status === 401) {
      this.logout();
      throw new Error('Sesión expirada');
    }

    return response;
  }
};
