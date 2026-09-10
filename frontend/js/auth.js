/**
 * Auth Module for App LTI - SSO Portal de Acceso Integration
 */

const Auth = {
  USER_KEY: 'app_lti_user',
  PORTAL_URL: 'https://200.14.222.162',
  _refreshPromise: null,

  getUser() {
    const raw = localStorage.getItem(this.USER_KEY) || sessionStorage.getItem(this.USER_KEY);
    try {
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  },

  setUser(user) {
    if (user) {
      localStorage.setItem(this.USER_KEY, JSON.stringify(user));
    } else {
      this.clearUser();
    }
  },

  clearUser() {
    localStorage.removeItem(this.USER_KEY);
    sessionStorage.removeItem(this.USER_KEY);
    localStorage.removeItem('app_lti_token');
  },

  redirectToLogin() {
    this.clearUser();
    window.location.href = `${this.PORTAL_URL}/`;
  },

  async refreshToken() {
    if (this._refreshPromise) {
      return this._refreshPromise;
    }

    this._refreshPromise = (async () => {
      try {
        const response = await fetch('/api/auth/refresh', {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json'
          }
        });
        if (!response.ok) {
          throw new Error('Refresh token fallido');
        }
        return true;
      } catch (err) {
        console.warn('[SSO Auth] Error al refrescar token:', err);
        return false;
      } finally {
        this._refreshPromise = null;
      }
    })();

    return this._refreshPromise;
  },

  getAppApiUrl(url) {
    if (!url || typeof url !== 'string') return url;
    if (url.startsWith('http://') || url.startsWith('https://')) return url;

    // Detectar si la SPA está montada bajo un subdirectorio como /app-lti
    const pathname = (typeof window !== 'undefined' && window.location && window.location.pathname) ? window.location.pathname : '';
    const basePath = pathname.startsWith('/app-lti') ? '/app-lti' : '';

    if (url.startsWith('/app-lti/')) {
      return url;
    }

    const cleanPath = url.startsWith('/') ? url : `/${url}`;
    return `${basePath}${cleanPath}`;
  },

  async authFetch(url, options = {}) {
    const finalUrl = this.getAppApiUrl(url);
    const opts = { ...options };
    opts.credentials = 'include';

    const isFormData = typeof FormData !== 'undefined' && opts.body instanceof FormData;
    let headers = {};

    if (typeof Headers !== 'undefined' && opts.headers instanceof Headers) {
      opts.headers.forEach((val, key) => {
        headers[key] = val;
      });
    } else if (opts.headers) {
      headers = { ...opts.headers };
    }

    if (!isFormData && !Object.keys(headers).some(k => k.toLowerCase() === 'content-type')) {
      headers['Content-Type'] = 'application/json';
    }

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

    opts.headers = headers;

    let response = await fetch(finalUrl, opts);

    // Si recibimos 401 Unauthorized y no estamos ya en el endpoint de refresh
    if (response.status === 401 && !url.includes('/api/auth/refresh')) {
      const refreshed = await this.refreshToken();
      if (refreshed) {
        response = await fetch(finalUrl, opts);
      } else {
        this.redirectToLogin();
        throw new Error('Sesión expirada en Portal de Acceso');
      }
    }

    return response;
  },

  async fetchWithAuth(url, options = {}) {
    return this.authFetch(url, options);
  },

  async getMe() {
    try {
      const response = await this.authFetch('/api/auth/me');
      if (response.ok) {
        const user = await response.json();
        // Normalización de rol en caso de faltar el claim directo
        if (!user.rol) {
          if (user.adminLevel >= 2 || user.is_super_admin || (user.roles && user.roles.includes('Super Admin'))) {
            user.rol = 'ADMIN';
          } else {
            user.rol = 'PM';
          }
        }
        this.setUser(user);
        return user;
      }
      return null;
    } catch (err) {
      console.warn('[SSO Auth] getMe falló:', err);
      return null;
    }
  },

  async checkSession() {
    return await this.getMe();
  },

  async logout() {
    try {
      await fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'include'
      });
    } catch (e) {
      // Ignorar error si el portal no responde
    }
    this.redirectToLogin();
  }
};
