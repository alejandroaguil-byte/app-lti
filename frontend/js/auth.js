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
    const headers = {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    };

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
