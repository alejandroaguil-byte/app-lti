/**
 * Main Application Script for App LTI
 */

const App = {
  currentProject: null,
  projectsData: [],
  lideresList: [],
  estadosSharepoint: [],
  activeTab: 'summary',
  activeDirectSearchTab: 'proyectos',
  currentModule: 'projects', // 'projects' | 'direct-search' | 'tickets' | 'solicitud-lti'
  searchTags: [], // Tags array for direct search module
  isTicketRunning: false,
  ticketLogCount: 0,
  ticketTimerInterval: null,
  ticketStartTime: null,
  ticketAutoScroll: true,
  ticketLogsRaw: [],
  solicitudCatalogosLoaded: false,
  solicitudLideresList: [],
  solicitudEstadosList: [],
  solicitudTiposServicioList: [],
  autocompleteResults: [],
  autocompleteSelectedIdx: -1,
  duplicateProjectId: null,
  isSolicitudSubmitting: false,
  lastLoadedSolotsText: '',

  init() {
    this.initTheme();
    this.bindEvents();
    
    if (Auth.isAuthenticated()) {
      this.showAppView();
      this.loadInitialData();
    } else {
      this.showAuthView();
    }
  },

  // --------------------------------------------------------------------------
  // THEME MANAGEMENT (Light / Dark Mode)
  // --------------------------------------------------------------------------
  initTheme() {
    const savedTheme = localStorage.getItem('app_lti_theme') || 'light';
    this.setTheme(savedTheme);

    const themeToggleBtn = document.getElementById('theme-toggle-btn');
    if (themeToggleBtn) {
      themeToggleBtn.addEventListener('click', () => {
        const current = document.documentElement.getAttribute('data-theme') || 'light';
        const next = current === 'dark' ? 'light' : 'dark';
        this.setTheme(next);
      });
    }
  },

  setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('app_lti_theme', theme);
    const icon = document.getElementById('theme-icon');
    if (icon) {
      icon.textContent = theme === 'dark' ? '☀️' : '🌙';
    }
  },

  // --------------------------------------------------------------------------
  // EVENT BINDINGS
  // --------------------------------------------------------------------------
  bindEvents() {
    // Top Module Navigation Buttons
    const navProjectsBtn = document.getElementById('nav-btn-projects');
    const navDirectSearchBtn = document.getElementById('nav-btn-direct-search');
    const navTicketsBtn = document.getElementById('nav-btn-tickets');
    const navSolicitudBtn = document.getElementById('nav-btn-solicitud-lti');

    if (navProjectsBtn) {
      navProjectsBtn.addEventListener('click', () => this.switchModule('projects'));
    }
    if (navDirectSearchBtn) {
      navDirectSearchBtn.addEventListener('click', () => this.switchModule('direct-search'));
    }
    if (navTicketsBtn) {
      navTicketsBtn.addEventListener('click', () => this.switchModule('tickets'));
    }
    if (navSolicitudBtn) {
      navSolicitudBtn.addEventListener('click', () => this.switchModule('solicitud-lti'));
    }

    // Login Form
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
      loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('login-username').value.trim();
        const password = document.getElementById('login-password').value;
        const errEl = document.getElementById('login-error');
        const btn = document.getElementById('login-submit-btn');

        errEl.textContent = '';
        btn.disabled = true;
        btn.textContent = 'Iniciando sesión...';

        try {
          await Auth.login(username, password);
          this.showAppView();
          this.loadInitialData();
        } catch (err) {
          errEl.textContent = err.message || 'Error de conexión';
        } finally {
          btn.disabled = false;
          btn.textContent = 'Iniciar Sesión';
        }
      });
    }

    // Logout Button
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
      logoutBtn.addEventListener('click', () => Auth.logout());
    }

    // Module 1 Filter changes
    const searchInput = document.getElementById('filter-search');
    if (searchInput) {
      const debouncedLoadProjects = this.debounce(() => this.loadProjects(), 300);
      searchInput.addEventListener('input', () => debouncedLoadProjects());
    }

    const estadoSpFilter = document.getElementById('filter-estado-sp');
    if (estadoSpFilter) {
      estadoSpFilter.addEventListener('change', () => this.loadProjects());
    }

    const ltFilter = document.getElementById('filter-lt');
    if (ltFilter) {
      ltFilter.addEventListener('change', () => {
        this.updateKPIActiveState();
        this.loadKPIs();
        this.loadProjects();
      });
    }

    // KPI Card Pendientes de Asignar (Interactive Click & Keydown)
    const kpiPendientesCard = document.getElementById('kpi-card-pendientes');
    if (kpiPendientesCard) {
      kpiPendientesCard.addEventListener('click', () => this.filterByUnassigned());
      kpiPendientesCard.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          this.filterByUnassigned();
        }
      });
    }

    // Back to projects button
    const backBtn = document.getElementById('back-to-projects-btn');
    if (backBtn) {
      backBtn.addEventListener('click', () => this.showProjectsList());
    }

    // Drill down tab buttons
    document.querySelectorAll('.tab-btn[data-tab]').forEach(btn => {
      btn.addEventListener('click', () => {
        this.switchTab(btn.dataset.tab);
      });
    });

    // Direct search tab buttons
    document.querySelectorAll('.tab-btn[data-search-tab]').forEach(btn => {
      btn.addEventListener('click', () => {
        this.switchDirectSearchTab(btn.dataset.searchTab);
      });
    });

    // Direct search Tag Input Events
    const tagInputField = document.getElementById('direct-search-input-field');
    if (tagInputField) {
      tagInputField.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ',') {
          e.preventDefault();
          const val = tagInputField.value.trim().replace(/^,|,$/g, '');
          if (val) {
            this.addSearchTag(val);
            tagInputField.value = '';
          } else if (this.searchTags.length > 0) {
            this.executeDirectSearch();
          }
        } else if (e.key === 'Backspace' && !tagInputField.value && this.searchTags.length > 0) {
          this.removeSearchTag(this.searchTags.length - 1);
        }
      });
    }

    const directSubmitBtn = document.getElementById('direct-search-submit-btn');
    if (directSubmitBtn) {
      directSubmitBtn.addEventListener('click', () => {
        const field = document.getElementById('direct-search-input-field');
        if (field && field.value.trim()) {
          this.addSearchTag(field.value.trim());
          field.value = '';
        }
        this.executeDirectSearch();
      });
    }

    const directClearBtn = document.getElementById('direct-search-clear-btn');
    if (directClearBtn) {
      directClearBtn.addEventListener('click', () => this.clearSearchTags());
    }

    // Export Button
    const exportBtn = document.getElementById('export-btn');
    if (exportBtn) {
      exportBtn.addEventListener('click', () => this.exportCurrentTableToCSV());
    }

    // Module 3: Ticket Automation Action Buttons
    const executeTicketBtn = document.getElementById('btn-execute-ticket');
    if (executeTicketBtn) {
      executeTicketBtn.addEventListener('click', () => this.executeTicketAutomation());
    }

    const clearLogsBtn = document.getElementById('btn-clear-logs');
    if (clearLogsBtn) {
      clearLogsBtn.addEventListener('click', () => this.clearTicketLogs());
    }

    const copyConsoleBtn = document.getElementById('btn-copy-console');
    if (copyConsoleBtn) {
      copyConsoleBtn.addEventListener('click', () => this.copyConsoleLogs());
    }

    const toggleAutoscrollBtn = document.getElementById('btn-toggle-autoscroll');
    if (toggleAutoscrollBtn) {
      toggleAutoscrollBtn.addEventListener('click', () => this.toggleAutoScroll());
    }

    // Ticket Success Modal Events
    const closeModalIcon = document.getElementById('btn-close-modal-icon');
    if (closeModalIcon) {
      closeModalIcon.addEventListener('click', () => this.closeSuccessModal());
    }

    const closeSuccessModalBtn = document.getElementById('btn-close-success-modal');
    if (closeSuccessModalBtn) {
      closeSuccessModalBtn.addEventListener('click', () => this.closeSuccessModal());
    }

    const ticketSuccessModal = document.getElementById('ticket-success-modal');
    if (ticketSuccessModal) {
      ticketSuccessModal.addEventListener('click', (e) => {
        if (e.target === ticketSuccessModal) {
          this.closeSuccessModal();
        }
      });
    }

    const copyTicketIdBtn = document.getElementById('btn-copy-ticket-id');
    if (copyTicketIdBtn) {
      copyTicketIdBtn.addEventListener('click', () => this.copyTicketIdToClipboard());
    }

    // Solicitud LTI: Autocomplete on N° Proyecto
    const projInput = document.getElementById('solicitud-nro-proyecto');
    if (projInput) {
      const debouncedAutocomplete = this.debounce((val) => this.handleAutocompleteInput(val), 250);
      projInput.addEventListener('input', () => {
        projInput.classList.remove('is-invalid');
        debouncedAutocomplete(projInput.value);
      });
      projInput.addEventListener('keydown', (e) => this.handleAutocompleteKeydown(e));
      projInput.addEventListener('blur', () => {
        const val = projInput.value.trim();
        if (val) {
          this.fetchAndFillSolotsLiray(val);
        }
      });
    }

    // Solicitud LTI: Close autocomplete dropdown when clicking outside
    document.addEventListener('click', (e) => {
      const autocompleteContainer = document.querySelector('.autocomplete-container');
      const dropdown = document.getElementById('solicitud-autocomplete-dropdown');
      if (dropdown && autocompleteContainer && !autocompleteContainer.contains(e.target)) {
        this.hideAutocompleteDropdown();
      }
    });

    // Clear validation error on field change/input
    ['solicitud-nro-proyecto', 'solicitud-cliente', 'solicitud-estado', 'solicitud-fecha', 'solicitud-detalle'].forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener('input', () => el.classList.remove('is-invalid'));
        el.addEventListener('change', () => el.classList.remove('is-invalid'));
      }
    });

    // Solicitud LTI: Submit & Reset buttons
    const submitSolBtn = document.getElementById('btn-submit-solicitud');
    if (submitSolBtn) {
      submitSolBtn.addEventListener('click', () => this.submitSolicitudForm());
    }

    const resetSolBtn = document.getElementById('btn-reset-solicitud');
    if (resetSolBtn) {
      resetSolBtn.addEventListener('click', () => this.resetSolicitudForm());
    }

    // Solicitud LTI: Duplicate view button
    const viewDupBtn = document.getElementById('btn-view-duplicate-project');
    if (viewDupBtn) {
      viewDupBtn.addEventListener('click', () => {
        if (this.duplicateProjectId) {
          this.switchModule('projects');
          this.drillDownById(this.duplicateProjectId);
        }
      });
    }

    // Solicitud LTI: Success modal events
    const closeSolModalIcon = document.getElementById('btn-close-solicitud-modal-icon');
    if (closeSolModalIcon) {
      closeSolModalIcon.addEventListener('click', () => this.closeSolicitudModal());
    }

    const solCreateAnotherBtn = document.getElementById('btn-solicitud-create-another');
    if (solCreateAnotherBtn) {
      solCreateAnotherBtn.addEventListener('click', () => {
        this.closeSolicitudModal();
        this.resetSolicitudForm();
      });
    }

    const solGoToProjectsBtn = document.getElementById('btn-solicitud-go-to-projects');
    if (solGoToProjectsBtn) {
      solGoToProjectsBtn.addEventListener('click', () => {
        this.closeSolicitudModal();
        this.switchModule('projects');
        this.loadProjects();
        this.loadKPIs();
      });
    }

    const solSuccessModal = document.getElementById('solicitud-success-modal');
    if (solSuccessModal) {
      solSuccessModal.addEventListener('click', (e) => {
        if (e.target === solSuccessModal) {
          this.closeSolicitudModal();
        }
      });
    }

    // Drill Down Edit / Delete Toolbar Buttons
    const btnDdEdit = document.getElementById('btn-dd-edit-project');
    if (btnDdEdit) {
      btnDdEdit.addEventListener('click', () => {
        if (this.currentProject) {
          this.openEditProjectModal(this.currentProject.ID);
        }
      });
    }

    const btnDdDelete = document.getElementById('btn-dd-delete-project');
    if (btnDdDelete) {
      btnDdDelete.addEventListener('click', () => {
        if (this.currentProject) {
          this.openDeleteProjectModal(this.currentProject.ID);
        }
      });
    }

    // Edit Project Modal Events
    const btnCloseEditIcon = document.getElementById('btn-close-edit-modal-icon');
    if (btnCloseEditIcon) {
      btnCloseEditIcon.addEventListener('click', () => this.closeEditProjectModal());
    }

    const btnCancelEdit = document.getElementById('btn-cancel-edit-modal');
    if (btnCancelEdit) {
      btnCancelEdit.addEventListener('click', () => this.closeEditProjectModal());
    }

    const btnSaveEdit = document.getElementById('btn-save-edit-modal');
    if (btnSaveEdit) {
      btnSaveEdit.addEventListener('click', () => this.submitEditProjectForm());
    }

    const editProjectModal = document.getElementById('edit-project-modal');
    if (editProjectModal) {
      editProjectModal.addEventListener('click', (e) => {
        if (e.target === editProjectModal) {
          this.closeEditProjectModal();
        }
      });
    }

    // Delete Project Modal Events
    const btnCloseDeleteIcon = document.getElementById('btn-close-delete-modal-icon');
    if (btnCloseDeleteIcon) {
      btnCloseDeleteIcon.addEventListener('click', () => this.closeDeleteProjectModal());
    }

    const btnCancelDelete = document.getElementById('btn-cancel-delete-modal');
    if (btnCancelDelete) {
      btnCancelDelete.addEventListener('click', () => this.closeDeleteProjectModal());
    }

    const btnConfirmDelete = document.getElementById('btn-confirm-delete-modal');
    if (btnConfirmDelete) {
      btnConfirmDelete.addEventListener('click', () => this.confirmDeleteProject());
    }

    const deleteProjectModal = document.getElementById('delete-project-modal');
    if (deleteProjectModal) {
      deleteProjectModal.addEventListener('click', (e) => {
        if (e.target === deleteProjectModal) {
          this.closeDeleteProjectModal();
        }
      });
    }

    // Global keyboard listener for modal
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        const modal = document.getElementById('ticket-success-modal');
        if (modal && modal.style.display !== 'none') {
          this.closeSuccessModal();
        }
        const solModal = document.getElementById('solicitud-success-modal');
        if (solModal && solModal.style.display !== 'none') {
          this.closeSolicitudModal();
        }
        const editModal = document.getElementById('edit-project-modal');
        if (editModal && editModal.style.display !== 'none') {
          this.closeEditProjectModal();
        }
        const delModal = document.getElementById('delete-project-modal');
        if (delModal && delModal.style.display !== 'none') {
          this.closeDeleteProjectModal();
        }
        this.hideAutocompleteDropdown();
      }
    });
  },

  debounce(func, wait) {
    let timeout;
    return (...args) => {
      clearTimeout(timeout);
      timeout = setTimeout(() => func.apply(this, args), wait);
    };
  },

  // --------------------------------------------------------------------------
  // MODULE SWITCHER
  // --------------------------------------------------------------------------
  switchModule(moduleName) {
    this.currentModule = moduleName;

    const navProjectsBtn = document.getElementById('nav-btn-projects');
    const navDirectSearchBtn = document.getElementById('nav-btn-direct-search');
    const navTicketsBtn = document.getElementById('nav-btn-tickets');
    const navSolicitudBtn = document.getElementById('nav-btn-solicitud-lti');

    const moduleProjects = document.getElementById('module-projects-container');
    const moduleDirectSearch = document.getElementById('module-direct-search-container');
    const moduleTickets = document.getElementById('module-tickets-container');
    const moduleSolicitud = document.getElementById('module-solicitud-lti-container');

    if (navProjectsBtn) navProjectsBtn.classList.toggle('active', moduleName === 'projects');
    if (navDirectSearchBtn) navDirectSearchBtn.classList.toggle('active', moduleName === 'direct-search');
    if (navTicketsBtn) navTicketsBtn.classList.toggle('active', moduleName === 'tickets');
    if (navSolicitudBtn) navSolicitudBtn.classList.toggle('active', moduleName === 'solicitud-lti');

    if (moduleProjects) {
      moduleProjects.style.display = moduleName === 'projects' ? 'block' : 'none';
      moduleProjects.classList.toggle('active', moduleName === 'projects');
    }
    if (moduleDirectSearch) {
      moduleDirectSearch.style.display = moduleName === 'direct-search' ? 'block' : 'none';
      moduleDirectSearch.classList.toggle('active', moduleName === 'direct-search');
    }
    if (moduleTickets) {
      moduleTickets.style.display = moduleName === 'tickets' ? 'block' : 'none';
      moduleTickets.classList.toggle('active', moduleName === 'tickets');
    }
    if (moduleSolicitud) {
      moduleSolicitud.style.display = moduleName === 'solicitud-lti' ? 'block' : 'none';
      moduleSolicitud.classList.toggle('active', moduleName === 'solicitud-lti');
    }

    if (moduleName === 'solicitud-lti') {
      this.loadSolicitudCatalogos();
      const fechaInput = document.getElementById('solicitud-fecha');
      if (fechaInput && !fechaInput.value) {
        const today = new Date();
        const year = today.getFullYear();
        const month = String(today.getMonth() + 1).padStart(2, '0');
        const day = String(today.getDate()).padStart(2, '0');
        fechaInput.value = `${year}-${month}-${day}`;
      }
    }
  },

  // --------------------------------------------------------------------------
  // VIEW NAVIGATION
  // --------------------------------------------------------------------------
  showAuthView() {
    const authView = document.getElementById('auth-view');
    if (authView) authView.style.display = 'flex';
    const appView = document.getElementById('app-view');
    if (appView) appView.style.display = 'none';
  },

  showAppView() {
    document.getElementById('auth-view').style.display = 'none';
    document.getElementById('app-view').style.display = 'block';

    const user = Auth.getUser();
    if (user) {
      const userDisplay = document.getElementById('user-display-name');
      if (userDisplay) {
        userDisplay.textContent = user.nombre_completo || user.username;
      }
      const userRole = document.getElementById('user-role-badge');
      if (userRole) {
        userRole.textContent = user.rol === 'ADMIN' ? 'Administrador' : 'Líder TI';
      }
    }

    this.switchModule(this.currentModule || 'projects');
  },

  showProjectsList() {
    document.getElementById('projects-list-section').style.display = 'block';
    document.getElementById('project-drilldown-section').style.display = 'none';
    this.currentProject = null;
  },

  showProjectDrilldown(project) {
    this.currentProject = project;
    document.getElementById('projects-list-section').style.display = 'none';
    document.getElementById('project-drilldown-section').style.display = 'block';
    
    // Render Drill Down Header Info
    document.getElementById('dd-client-title').textContent = project.Cliente || 'Sin Título';
    document.getElementById('dd-proj-num').textContent = this.formatNumeroProyecto(project.Numero_Proyecto);
    document.getElementById('dd-lt-assigned').textContent = project.LT_Asignado || 'No asignado';
    document.getElementById('dd-status').innerHTML = this.renderStatusBadge(project.Estado);
    
    this.switchTab('summary');
    this.loadProjectDetails(project.ID);
  },

  // --------------------------------------------------------------------------
  // DATA LOADING (MODULE 1)
  // --------------------------------------------------------------------------
  async loadInitialData() {
    await Promise.all([
      this.loadLideres(),
      this.loadEstados(),
      this.loadKPIs()
    ]);
    await this.loadProjects();
  },

  async loadLideres() {
    try {
      const res = await Auth.fetchWithAuth('/api/lideres');
      this.lideresList = await res.json();
      
      const select = document.getElementById('filter-lt');
      if (select) {
        const user = Auth.getUser();
        select.innerHTML = '';

        // 1. Opción por defecto
        const allOption = document.createElement('option');
        allOption.value = '__ALL__';
        allOption.textContent = '— Todos los Líderes TI —';
        select.appendChild(allOption);

        // 2. Opción Sin Asignar
        const unassignedOption = document.createElement('option');
        unassignedOption.value = '__UNASSIGNED__';
        unassignedOption.textContent = 'Sin asignar';
        select.appendChild(unassignedOption);

        // 3. Opciones de Líderes en Orden Alfabético Estricto
        this.lideresList.forEach(lt => {
          const opt = document.createElement('option');
          opt.value = lt;
          opt.textContent = lt;
          if (user && user.lt_asignado === lt && user.rol !== 'ADMIN') {
            opt.selected = true;
          }
          select.appendChild(opt);
        });

        if (user && user.rol === 'ADMIN') {
          allOption.selected = true;
        }

        this.updateKPIActiveState();
      }
    } catch (e) {
      console.error('Error al cargar líderes:', e);
    }
  },

  async loadEstados() {
    try {
      const res = await Auth.fetchWithAuth('/api/estados');
      const data = await res.json();
      this.estadosSharepoint = data.estados_sharepoint || [];

      const selectSp = document.getElementById('filter-estado-sp');
      if (selectSp) {
        selectSp.innerHTML = '<option value="">— Estado Sharepoint (Todos) —</option>';
        this.estadosSharepoint.forEach(est => {
          const opt = document.createElement('option');
          opt.value = est;
          opt.textContent = est;
          selectSp.appendChild(opt);
        });
      }
    } catch (e) {
      console.error('Error al cargar estados:', e);
    }
  },

  async loadKPIs() {
    try {
      const ltFilter = document.getElementById('filter-lt')?.value || '';
      let url = '/api/kpis';
      if (ltFilter) {
        url += `?lt=${encodeURIComponent(ltFilter)}`;
      }
      
      const res = await Auth.fetchWithAuth(url);
      const kpis = await res.json();

      const valProyectos = document.getElementById('kpi-val-proyectos');
      const valEnCurso = document.getElementById('kpi-val-en-curso');
      const valPendientes = document.getElementById('kpi-val-pendientes-asignar');
      const valEfectividad = document.getElementById('kpi-val-efectividad');
      const valTickets = document.getElementById('kpi-val-tickets');
      const valRfcs = document.getElementById('kpi-val-rfcs');

      if (valProyectos) valProyectos.textContent = kpis.total_proyectos || 0;
      if (valEnCurso) valEnCurso.textContent = kpis.proyectos_en_curso || 0;
      if (valPendientes) valPendientes.textContent = kpis.pendientes_asignar || 0;
      if (valEfectividad) valEfectividad.textContent = `${kpis.efectividad !== undefined ? kpis.efectividad : 0}%`;
      if (valTickets) valTickets.textContent = kpis.total_tickets || 0;
      if (valRfcs) valRfcs.textContent = kpis.total_rfcs || 0;

      this.updateKPIActiveState();
    } catch (e) {
      console.error('Error al cargar KPIs:', e);
    }
  },

  filterByUnassigned() {
    const select = document.getElementById('filter-lt');
    if (select) {
      if (select.value === '__UNASSIGNED__') {
        select.value = '__ALL__';
      } else {
        select.value = '__UNASSIGNED__';
      }
      this.updateKPIActiveState();
      this.loadKPIs();
      this.loadProjects();
      if (select.value === '__UNASSIGNED__') {
        this.showToast('Filtrando proyectos pendientes de asignar Líder TI', 'info');
      } else {
        this.showToast('Mostrando todos los proyectos', 'info');
      }
    }
  },

  updateKPIActiveState() {
    const currentLt = document.getElementById('filter-lt')?.value || '';
    const kpiPendientesCard = document.getElementById('kpi-card-pendientes');
    if (kpiPendientesCard) {
      const isUnassigned = currentLt === '__UNASSIGNED__';
      if (isUnassigned) {
        kpiPendientesCard.classList.add('active-filter');
        kpiPendientesCard.setAttribute('aria-pressed', 'true');
      } else {
        kpiPendientesCard.classList.remove('active-filter');
        kpiPendientesCard.setAttribute('aria-pressed', 'false');
      }
    }
  },

  async loadProjects() {
    const tbody = document.getElementById('projects-table-body');
    if (!tbody) return;

    tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 2rem;"><span class="badge badge-info">Cargando proyectos...</span></td></tr>`;

    const search = document.getElementById('filter-search')?.value || '';
    const estadoSp = document.getElementById('filter-estado-sp')?.value || '';
    const lt = document.getElementById('filter-lt')?.value || '';

    const params = new URLSearchParams();
    if (search) params.append('search', search);
    if (estadoSp) params.append('estado_sp', estadoSp);
    if (lt) params.append('lt', lt);

    try {
      const res = await Auth.fetchWithAuth(`/api/proyectos?${params.toString()}`);
      this.projectsData = await res.json();
      this.renderProjectsTable(this.projectsData);

      // Update count badge
      const countBadge = document.getElementById('projects-count-badge');
      if (countBadge) {
        countBadge.textContent = this.projectsData.length;
      }
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 2rem; color: var(--status-danger-text);">Error al cargar proyectos: ${e.message}</td></tr>`;
      const countBadge = document.getElementById('projects-count-badge');
      if (countBadge) countBadge.textContent = '0';
    }
  },

  renderProjectsTable(proyectos) {
    const tbody = document.getElementById('projects-table-body');
    if (!proyectos || proyectos.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="8">
            <div class="empty-state">
              <div class="empty-icon">📁</div>
              <h3>No se encontraron proyectos</h3>
              <p>Intenta ajustar los filtros de búsqueda o seleccionar otro Líder TI / Estado.</p>
            </div>
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = proyectos.map(p => {
      const solicitanteFormatted = this.formatSolicitante(p.Solicitante);
      const isUnmatched = solicitanteFormatted.startsWith('NO IDENTIFICADO');
      return `
        <tr>
          <td>
            <div class="col-project-client" title="${this.escapeHtml(p.Cliente || '')}">
              ${this.escapeHtml(p.Cliente || 'Sin título')}
            </div>
          </td>
          <td><span style="font-family: var(--font-mono); font-weight: 700; color: var(--primary); white-space: nowrap;">${this.escapeHtml(this.formatNumeroProyecto(p.Numero_Proyecto))}</span></td>
          <td style="white-space: nowrap;">${this.escapeHtml(p.LT_Asignado || 'No asignado')}</td>
          <td class="col-solicitante" title="${this.escapeHtml(solicitanteFormatted)}">
            ${isUnmatched 
              ? `<span class="unmatched-solicitante">${this.escapeHtml(solicitanteFormatted)}</span>` 
              : `<strong>${this.escapeHtml(solicitanteFormatted)}</strong>`
            }
          </td>
          <td style="white-space: nowrap;">${this.renderStatusBadge(p.Estado)}</td>
          <td style="white-space: nowrap;"><small style="color: var(--text-secondary); font-weight: 600;">${this.formatDateDMY(p.Creado)}</small></td>
          <td class="col-project-detalle" title="${this.escapeHtml(p.Detalle || '')}">
            ${this.escapeHtml(p.Detalle || 'Sin detalle')}
          </td>
          <td class="col-action-cell">
            <div class="action-buttons-group">
              <button type="button" class="btn-action-icon btn-action-view" onclick="App.drillDownById(${p.ID})" title="Ver detalle completo (Drill Down)" aria-label="Ver Detalle">
                🔍
              </button>
              <button type="button" class="btn-action-icon btn-action-edit" onclick="App.openEditProjectModal(${p.ID})" title="Editar proyecto" aria-label="Editar Proyecto">
                ✏️
              </button>
              <button type="button" class="btn-action-icon btn-action-delete" onclick="App.openDeleteProjectModal(${p.ID})" title="Eliminar proyecto" aria-label="Eliminar Proyecto">
                🗑️
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join('');
  },

  drillDownById(projectId) {
    Auth.fetchWithAuth(`/api/proyectos/${projectId}`)
      .then(async (r) => {
        if (!r.ok) {
          const err = await r.json().catch(() => ({ detail: 'Proyecto no encontrado' }));
          throw new Error(err.detail || 'Proyecto no encontrado');
        }
        return r.json();
      })
      .then(p => this.showProjectDrilldown(p))
      .catch(err => this.showToast(`Error al cargar detalle: ${err.message}`, 'danger'));
  },

  // --------------------------------------------------------------------------
  // DRILL-DOWN TABS & TIMELINE (MODULE 1)
  // --------------------------------------------------------------------------
  switchTab(tabId) {
    this.activeTab = tabId;
    
    document.querySelectorAll('.tab-btn[data-tab]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === tabId);
    });

    document.querySelectorAll('.tab-pane').forEach(pane => {
      pane.style.display = pane.id === `tab-pane-${tabId}` ? 'block' : 'none';
    });
  },

  async loadProjectDetails(projectId) {
    this.renderSummaryTab(this.currentProject);
    this.renderProjectTimeline(this.currentProject);
    this.loadSolots(projectId);
    this.loadTickets(projectId);
    this.loadRFCs(projectId);
  },

  renderProjectTimeline(p) {
    const track = document.getElementById('timeline-track-steps');
    if (!track) return;

    // Define 4 milestones
    const rawMilestones = [
      {
        id: 'creacion_sga',
        title: 'Fecha Creación Proyecto SGA',
        date: p.fecha_creacion_sga,
        source: 'CT_BACKLOG_OPERACIONES2 (FECHA_INSERT)'
      },
      {
        id: 'solicitud_lti',
        title: 'Fecha Solicitud LTI',
        date: p.fecha_solicitud_lti || p.Creado,
        source: 'Proyectos (Creado)'
      },
      {
        id: 'compromiso_sga',
        title: 'Fecha Compromiso Proyecto',
        date: p.fecha_compromiso_sga,
        source: 'CT_BACKLOG_OPERACIONES2 (FECHA_COMPROMETIDA)'
      },
      {
        id: 'cierre_sga',
        title: 'Fecha Cierre Proyecto',
        date: p.fecha_cierre_sga,
        source: 'CT_BACKLOG_OPERACIONES2 (FECHA_REALIZACION)'
      }
    ];

    // Separate established dates vs pending dates
    const established = rawMilestones.filter(m => !!m.date);
    const pending = rawMilestones.filter(m => !m.date);

    // Sort established chronologically (de menor a mayor)
    established.sort((a, b) => new Date(a.date) - new Date(b.date));

    // Combine ordered milestones
    const ordered = [...established, ...pending];

    let timelineHtml = '';
    for (let i = 0; i < ordered.length; i++) {
      const m = ordered[i];
      const isCompleted = !!m.date;
      const formattedDate = isCompleted ? this.formatDateDMY(m.date) : 'Pendiente / No registrada';
      const stepNumber = i + 1;

      // Render Step Node
      timelineHtml += `
        <div class="timeline-step ${isCompleted ? 'completed' : 'pending'}">
          <div class="timeline-dot" title="${this.escapeHtml(m.source)}">
            ${isCompleted ? '✓' : stepNumber}
          </div>
          <div class="timeline-milestone-title">${this.escapeHtml(m.title)}</div>
          <div class="timeline-date-badge">${formattedDate}</div>
        </div>
      `;

      // Render Connector with days calculation between current and next milestone
      if (i < ordered.length - 1) {
        const nextM = ordered[i + 1];
        if (m.date && nextM.date) {
          const d1 = new Date(m.date);
          const d2 = new Date(nextM.date);
          const diffMs = Math.abs(d2.getTime() - d1.getTime());
          const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24));
          const daysLabel = diffDays === 1 ? '1 día' : `${diffDays} días`;

          timelineHtml += `
            <div class="timeline-connector completed">
              <div class="timeline-connector-line"></div>
              <div class="timeline-duration-badge" title="Diferencia de tiempo entre hitos">⏱️ ${daysLabel}</div>
            </div>
          `;
        } else {
          timelineHtml += `
            <div class="timeline-connector">
              <div class="timeline-connector-line"></div>
              <div class="timeline-duration-badge" style="color: var(--text-muted); font-style: italic;">—</div>
            </div>
          `;
        }
      }
    }

    track.innerHTML = timelineHtml;
  },

  renderSummaryTab(p) {
    const container = document.getElementById('summary-content');
    if (!container) return;

    container.innerHTML = `
      <div class="detail-grid">
        <div class="detail-card">
          <div class="detail-card-title">Información Principal</div>
          <div class="detail-row">
            <span class="detail-label">Cliente:</span>
            <span class="detail-val">${this.escapeHtml(p.Cliente || 'N/A')}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">N° Proyecto:</span>
            <span class="detail-val" style="font-family: var(--font-mono); color: var(--primary);">${this.escapeHtml(this.formatNumeroProyecto(p.Numero_Proyecto))}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">LT Asignado:</span>
            <span class="detail-val">${this.escapeHtml(p.LT_Asignado || 'N/A')}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Estado:</span>
            <span class="detail-val">${this.renderStatusBadge(p.Estado)}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Solicitante:</span>
            <span class="detail-val">${this.escapeHtml(this.formatSolicitante(p.Solicitante))}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Fecha Solicitud LTI:</span>
            <span class="detail-val">${this.formatDateDMY(p.Creado)}</span>
          </div>
        </div>

        <div class="detail-card">
          <div class="detail-card-title">Detalle Técnico & Clasificación</div>
          <div class="detail-row">
            <span class="detail-label">Tipo de Servicio:</span>
            <span class="detail-val">${this.escapeHtml(p.Tipo_Servicio || 'No especificado')}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Total Solots Backlog:</span>
            <span class="detail-val"><span class="badge badge-success">${p.total_solots || 0}</span></span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Total Tickets SD:</span>
            <span class="detail-val"><span class="badge badge-warning">${p.total_tickets || 0}</span></span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Total RFCs:</span>
            <span class="detail-val"><span class="badge badge-info">${p.total_rfcs || 0}</span></span>
          </div>
          <div style="margin-top: 1rem;">
            <span class="detail-label" style="display: block; margin-bottom: 0.3rem;">Detalle del Proyecto:</span>
            <p style="background: var(--bg-surface-secondary); padding: 0.75rem; border-radius: var(--radius-sm); font-size: 0.88rem; line-height: 1.4; white-space: pre-wrap;">
              ${this.escapeHtml(p.Detalle || 'Sin descripción o detalle adicional')}
            </p>
          </div>
          <div style="margin-top: 1rem;">
            <span class="detail-label" style="display: block; margin-bottom: 0.3rem;">Comentarios de Cierre:</span>
            ${(p.Estado && p.Estado.toLowerCase().trim() === 'atendido' && p.Comentario && p.Comentario.trim()) 
              ? `<p style="background: var(--bg-surface-secondary); padding: 0.75rem; border-radius: var(--radius-sm); font-size: 0.88rem; line-height: 1.4; border-left: 3px solid var(--status-success-text); white-space: pre-wrap;">${this.escapeHtml(p.Comentario)}</p>`
              : `<p style="background: var(--bg-surface-secondary); padding: 0.75rem; border-radius: var(--radius-sm); font-size: 0.88rem; line-height: 1.4; color: var(--text-muted); font-style: italic;">Sin comentarios de cierre</p>`
            }
          </div>
        </div>
      </div>
    `;
  },

  async loadSolots(projectId) {
    const tbody = document.getElementById('solots-table-body');
    const badge = document.getElementById('tab-count-solots');
    tbody.innerHTML = `<tr><td colspan="11" style="text-align: center; padding: 1.5rem;">Cargando Solots...</td></tr>`;

    try {
      const res = await Auth.fetchWithAuth(`/api/proyectos/${projectId}/solots`);
      const solots = await res.json();
      if (badge) badge.textContent = solots.length;

      if (!solots || solots.length === 0) {
        tbody.innerHTML = `<tr><td colspan="11" class="empty-state"><p>No existen Solots asociadas a este proyecto en CT_BACKLOG_OPERACIONES2.</p></td></tr>`;
        return;
      }

      tbody.innerHTML = solots.map(s => `
        <tr>
          <td>${this.escapeHtml(s.ID_CLI || 'N/A')}</td>
          <td><strong style="color: var(--primary);">${this.escapeHtml(s.NRO_PROYECTO || 'N/A')}</strong></td>
          <td><span style="font-family: var(--font-mono); font-weight: 700;">${this.escapeHtml(s.ID_OTP || 'N/A')}</span></td>
          <td style="max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(s.DESCR_OTP || '')}">
            ${this.escapeHtml(s.DESCR_OTP || '-')}
          </td>
          <td>${this.renderStatusBadge(s.ESTADO_OTP)}</td>
          <td><small>${this.formatDateDMY(s.FECHA_COMPROMETIDA)}</small></td>
          <td><small>${this.formatDateDMY(s.FECHA_INSERT)}</small></td>
          <td>${this.escapeHtml(s.PLAZO_CONTRATO || '-')}</td>
          <td>${this.escapeHtml(s.PRODUCTO || '-')}</td>
          <td>${this.escapeHtml(s.SERVICIO || '-')}</td>
          <td>${this.escapeHtml(s.NRO_SERVICIO || '-')}</td>
        </tr>
      `).join('');
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="11" style="color: var(--status-danger-text); text-align: center;">Error: ${e.message}</td></tr>`;
    }
  },

  async loadTickets(projectId) {
    const tbody = document.getElementById('tickets-table-body');
    const badge = document.getElementById('tab-count-tickets');
    tbody.innerHTML = `<tr><td colspan="11" style="text-align: center; padding: 1.5rem;">Cargando Tickets...</td></tr>`;

    try {
      const res = await Auth.fetchWithAuth(`/api/proyectos/${projectId}/tickets`);
      const tickets = await res.json();
      if (badge) badge.textContent = tickets.length;

      if (!tickets || tickets.length === 0) {
        tbody.innerHTML = `<tr><td colspan="11" class="empty-state"><p>No existen tickets asociados en registrosRF_SD_SM.</p></td></tr>`;
        return;
      }

      tbody.innerHTML = tickets.map(t => `
        <tr>
          <td><strong style="color: var(--primary); font-family: var(--font-mono);">${this.escapeHtml(t.CC_INCIDENT_ID || 'N/A')}</strong></td>
          <td>${this.escapeHtml(t.REQUESTOR_NAME || '-')}</td>
          <td>${this.renderStatusBadge(t.STATUS)}</td>
          <td><small>${this.formatDateDMY(t.SUBMIT_DATE)}</small></td>
          <td><small>${this.formatDateDMY(t.CLOSE_DATE)}</small></td>
          <td style="max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(t.BRIEF_DESCRIPTION || '')}">
            ${this.escapeHtml(t.BRIEF_DESCRIPTION || '-')}
          </td>
          <td>${this.escapeHtml(t.CATEGORY || '-')}</td>
          <td>${this.escapeHtml(t.CC_DETALLE_SERVICIO || '-')}</td>
          <td>${this.escapeHtml(t.ASSIGNED_GROUP || '-')}</td>
          <td>${this.escapeHtml(t.ASSIGNED_TO || '-')}</td>
          <td><span style="font-family: var(--font-mono);">${this.escapeHtml(t.RF_ID || '-')}</span></td>
        </tr>
      `).join('');
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="11" style="color: var(--status-danger-text); text-align: center;">Error: ${e.message}</td></tr>`;
    }
  },

  async loadRFCs(projectId) {
    const tbody = document.getElementById('rfcs-table-body');
    const badge = document.getElementById('tab-count-rfcs');
    tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 1.5rem;">Cargando RFCs...</td></tr>`;

    try {
      const res = await Auth.fetchWithAuth(`/api/proyectos/${projectId}/rfcs`);
      const rfcs = await res.json();
      if (badge) badge.textContent = rfcs.length;

      if (!rfcs || rfcs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" class="empty-state"><p>No existen RFCs asociadas en registrosSM_RFC.</p></td></tr>`;
        return;
      }

      tbody.innerHTML = rfcs.map(r => `
        <tr>
          <td><strong style="color: var(--primary); font-family: var(--font-mono);">${this.escapeHtml(r.NUMBER || 'N/A')}</strong></td>
          <td style="max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(r.BRIEF_DESCRIPTION || '')}">
            ${this.escapeHtml(r.BRIEF_DESCRIPTION || '-')}
          </td>
          <td style="max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(r.DESCRIPTION || '')}">
            ${this.escapeHtml(r.DESCRIPTION || '-')}
          </td>
          <td>${this.escapeHtml(r.REQUESTED_BY || '-')}</td>
          <td><small>${this.formatDateDMY(r.CLOSE_TIME)}</small></td>
          <td><span style="font-family: var(--font-mono);">${this.escapeHtml(r.CC_PROYECT_NUMBER || '-')}</span></td>
          <td>${this.escapeHtml(r.CC_SERVICIO_PADRE || '-')}</td>
          <td>${this.escapeHtml(r.ASSIGN_DEPT || '-')}</td>
          <td>${this.escapeHtml(r.ASSIGNED_TO || '-')}</td>
        </tr>
      `).join('');
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="9" style="color: var(--status-danger-text); text-align: center;">Error: ${e.message}</td></tr>`;
    }
  },

  // --------------------------------------------------------------------------
  // MULTI-TAG SEARCH LOGIC (MODULE 2)
  // --------------------------------------------------------------------------
  addSearchTag(tagText) {
    const trimmed = tagText.trim();
    if (trimmed && !this.searchTags.includes(trimmed)) {
      this.searchTags.push(trimmed);
      this.renderSearchTags();
      this.executeDirectSearch();
    }
  },

  removeSearchTag(index) {
    this.searchTags.splice(index, 1);
    this.renderSearchTags();
    if (this.searchTags.length > 0) {
      this.executeDirectSearch();
    } else {
      document.getElementById('direct-search-results-area').style.display = 'none';
      document.getElementById('direct-search-empty-state').style.display = 'block';
    }
  },

  clearSearchTags() {
    this.searchTags = [];
    this.renderSearchTags();
    const inputField = document.getElementById('direct-search-input-field');
    if (inputField) inputField.value = '';
    document.getElementById('direct-search-results-area').style.display = 'none';
    document.getElementById('direct-search-empty-state').style.display = 'block';
  },

  renderSearchTags() {
    const container = document.getElementById('tags-rendered-list');
    if (!container) return;

    container.innerHTML = this.searchTags.map((tag, idx) => `
      <span class="tag-badge-item">
        <span>${this.escapeHtml(tag)}</span>
        <button type="button" class="tag-remove-btn" onclick="App.removeSearchTag(${idx})" title="Eliminar tag">×</button>
      </span>
    `).join('');
  },

  switchDirectSearchTab(tabName) {
    this.activeDirectSearchTab = tabName;

    document.querySelectorAll('.tab-btn[data-search-tab]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.searchTab === tabName);
    });

    document.querySelectorAll('.direct-tab-pane').forEach(pane => {
      pane.style.display = pane.id === `direct-tab-pane-${tabName}` ? 'block' : 'none';
    });
  },

  async executeDirectSearch() {
    const tableSelect = document.getElementById('direct-search-table-select');
    const btn = document.getElementById('direct-search-submit-btn');
    const resultsArea = document.getElementById('direct-search-results-area');
    const emptyState = document.getElementById('direct-search-empty-state');

    if (this.searchTags.length === 0) {
      const inputField = document.getElementById('direct-search-input-field');
      const val = inputField?.value.trim();
      if (val) {
        this.addSearchTag(val);
        inputField.value = '';
        return;
      } else {
        alert('Ingresa al menos un término o tag de búsqueda.');
        return;
      }
    }

    const table = tableSelect?.value || 'all';
    btn.disabled = true;
    btn.textContent = 'Buscando...';

    const params = new URLSearchParams();
    this.searchTags.forEach(t => params.append('tags', t));
    params.append('table', table);
    params.append('limit', '200');

    try {
      const res = await Auth.fetchWithAuth(`/api/search/direct?${params.toString()}`);
      const data = await res.json();

      emptyState.style.display = 'none';
      resultsArea.style.display = 'block';

      // Update badges
      document.getElementById('badge-count-direct-proyectos').textContent = data.counts.proyectos || 0;
      document.getElementById('badge-count-direct-solots').textContent = data.counts.solots || 0;
      document.getElementById('badge-count-direct-tickets').textContent = data.counts.tickets || 0;
      document.getElementById('badge-count-direct-rfcs').textContent = data.counts.rfcs || 0;

      // Render Table 1: Proyectos
      this.renderDirectProyectos(data.proyectos || []);

      // Render Table 2: Solots
      this.renderDirectSolots(data.solots || []);

      // Render Table 3: Tickets
      this.renderDirectTickets(data.tickets || []);

      // Render Table 4: RFCs
      this.renderDirectRFCs(data.rfcs || []);

      // Auto-switch to tab with results if current is empty
      if (data.counts[this.activeDirectSearchTab] === 0) {
        if (data.counts.proyectos > 0) this.switchDirectSearchTab('proyectos');
        else if (data.counts.solots > 0) this.switchDirectSearchTab('solots');
        else if (data.counts.tickets > 0) this.switchDirectSearchTab('tickets');
        else if (data.counts.rfcs > 0) this.switchDirectSearchTab('rfcs');
      }

    } catch (e) {
      alert(`Error en búsqueda: ${e.message}`);
    } finally {
      btn.disabled = false;
      btn.textContent = 'Buscar en BD';
    }
  },

  renderDirectProyectos(list) {
    const tbody = document.getElementById('direct-proyectos-table-body');
    if (!list || list.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="empty-state"><p>No se encontraron proyectos coincidentes con los tags seleccionados.</p></td></tr>`;
      return;
    }
    tbody.innerHTML = list.map(p => `
      <tr>
        <td><span style="font-family: var(--font-mono); font-weight: 700;">${p.ID}</span></td>
        <td><strong>${this.escapeHtml(p.Cliente || '-')}</strong></td>
        <td><span style="font-family: var(--font-mono); color: var(--primary);">${this.escapeHtml(p.Numero_Proyecto || '-')}</span></td>
        <td>${this.escapeHtml(p.LT_Asignado || '-')}</td>
        <td>${this.renderStatusBadge(p.Estado)}</td>
        <td><small style="color: var(--text-secondary); font-weight: 600;">${this.formatDateDMY(p.Creado)}</small></td>
        <td>${this.escapeHtml(p.Tipo_Servicio || '-')}</td>
        <td style="max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(p.Detalle || '')}">
          ${this.escapeHtml(p.Detalle || '-')}
        </td>
      </tr>
    `).join('');
  },

  renderDirectSolots(list) {
    const tbody = document.getElementById('direct-solots-table-body');
    if (!list || list.length === 0) {
      tbody.innerHTML = `<tr><td colspan="12" class="empty-state"><p>No se encontraron registros coincidentes en dbo.CT_BACKLOG_OPERACIONES2.</p></td></tr>`;
      return;
    }
    tbody.innerHTML = list.map(s => `
      <tr>
        <td><strong style="color: var(--primary); font-family: var(--font-mono);">${this.escapeHtml(s.ID_OTP || '-')}</strong></td>
        <td><span style="font-family: var(--font-mono);">${this.escapeHtml(s.NRO_PROYECTO || '-')}</span></td>
        <td>${this.escapeHtml(s.CLI_CLIENTE || '-')}</td>
        <td>${this.escapeHtml(s.ID_CLI || '-')}</td>
        <td>${this.escapeHtml(s.RUT_CLIENTE || '-')}</td>
        <td>${this.renderStatusBadge(s.ESTADO_OTP)}</td>
        <td style="max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(s.DESCR_OTP || '')}">
          ${this.escapeHtml(s.DESCR_OTP || '-')}
        </td>
        <td><small>${this.formatDateDMY(s.FECHA_INSERT)}</small></td>
        <td><small>${this.formatDateDMY(s.FECHA_COMPROMETIDA)}</small></td>
        <td>${this.escapeHtml(s.PRODUCTO || '-')}</td>
        <td>${this.escapeHtml(s.SERVICIO || '-')}</td>
        <td>${this.escapeHtml(s.ASIGNADO_OTP || '-')}</td>
      </tr>
    `).join('');
  },

  renderDirectTickets(list) {
    const tbody = document.getElementById('direct-tickets-table-body');
    if (!list || list.length === 0) {
      tbody.innerHTML = `<tr><td colspan="11" class="empty-state"><p>No se encontraron registros coincidentes en dbo.registrosRF_SD_SM.</p></td></tr>`;
      return;
    }
    tbody.innerHTML = list.map(t => `
      <tr>
        <td><strong style="color: var(--primary); font-family: var(--font-mono);">${this.escapeHtml(t.CC_INCIDENT_ID || '-')}</strong></td>
        <td><span style="font-family: var(--font-mono);">${this.escapeHtml(t.RF_ID || '-')}</span></td>
        <td>${this.escapeHtml(t.REQUESTOR_NAME || '-')}</td>
        <td>${this.renderStatusBadge(t.STATUS)}</td>
        <td><small>${this.formatDateDMY(t.SUBMIT_DATE)}</small></td>
        <td><small>${this.formatDateDMY(t.CLOSE_DATE)}</small></td>
        <td style="max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(t.BRIEF_DESCRIPTION || '')}">
          ${this.escapeHtml(t.BRIEF_DESCRIPTION || '-')}
        </td>
        <td>${this.escapeHtml(t.CATEGORY || '-')}</td>
        <td>${this.escapeHtml(t.CC_DETALLE_SERVICIO || '-')}</td>
        <td>${this.escapeHtml(t.ASSIGNED_GROUP || '-')}</td>
        <td>${this.escapeHtml(t.ASSIGNED_TO || '-')}</td>
      </tr>
    `).join('');
  },

  renderDirectRFCs(list) {
    const tbody = document.getElementById('direct-rfcs-table-body');
    if (!list || list.length === 0) {
      tbody.innerHTML = `<tr><td colspan="10" class="empty-state"><p>No se encontraron registros coincidentes en dbo.registrosSM_RFC.</p></td></tr>`;
      return;
    }
    tbody.innerHTML = list.map(r => `
      <tr>
        <td><strong style="color: var(--primary); font-family: var(--font-mono);">${this.escapeHtml(r.NUMBER || '-')}</strong></td>
        <td><span style="font-family: var(--font-mono);">${this.escapeHtml(r.CC_PROYECT_NUMBER || '-')}</span></td>
        <td style="max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(r.BRIEF_DESCRIPTION || '')}">
          ${this.escapeHtml(r.BRIEF_DESCRIPTION || '-')}
        </td>
        <td style="max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(r.DESCRIPTION || '')}">
          ${this.escapeHtml(r.DESCRIPTION || '-')}
        </td>
        <td>${this.escapeHtml(r.REQUESTED_BY || '-')}</td>
        <td>${this.escapeHtml(r.CC_SERVICIO_PADRE || '-')}</td>
        <td>${this.escapeHtml(r.ASSIGN_DEPT || '-')}</td>
        <td>${this.escapeHtml(r.ASSIGNED_TO || '-')}</td>
        <td><small>${this.formatDateDMY(r.ORIG_DATE_ENTERED)}</small></td>
        <td><small>${this.formatDateDMY(r.CLOSE_TIME)}</small></td>
      </tr>
    `).join('');
  },

  // --------------------------------------------------------------------------
  // MODULE 3: AUTOMATED TICKET GENERATOR (SERVICE MANAGER SSE)
  // --------------------------------------------------------------------------
  async executeTicketAutomation() {
    if (this.isTicketRunning) return;

    // Read form input values
    const contactoEl = document.getElementById('ticket-contacto');
    const tituloEl = document.getElementById('ticket-titulo');
    const descripcionEl = document.getElementById('ticket-descripcion');
    const areaEl = document.getElementById('ticket-area');
    const subareaEl = document.getElementById('ticket-subarea');
    const detalleEl = document.getElementById('ticket-detalle');
    const grupoEl = document.getElementById('ticket-grupo');
    const impactoEl = document.getElementById('ticket-impacto');
    const urgenciaEl = document.getElementById('ticket-urgencia');

    const payload = {
      contacto: contactoEl ? contactoEl.value.trim() : '',
      titulo: tituloEl ? tituloEl.value.trim() : '',
      descripcion: descripcionEl ? descripcionEl.value.trim() : '',
      area: areaEl ? areaEl.value.trim() : '',
      subarea: subareaEl ? subareaEl.value.trim() : '',
      detalle: detalleEl ? detalleEl.value.trim() : '',
      grupo: grupoEl ? grupoEl.value.trim() : '',
      impacto: impactoEl ? impactoEl.value.trim() : '',
      urgencia: urgenciaEl ? urgenciaEl.value.trim() : '',
      headless: true
    };

    // Validation: check required fields
    if (!payload.contacto || !payload.titulo || !payload.descripcion || !payload.area || !payload.subarea || !payload.detalle || !payload.grupo) {
      alert('Por favor completa todos los campos obligatorios (*) antes de iniciar la automatización.');
      return;
    }

    // Set UI to running state
    this.setTicketExecutionState(true);
    this.updateTicketProgress(5);
    this.updateTicketStatus('running', 'En ejecución', 'Iniciando conexión con el servicio...');

    // Start timer
    this.ticketStartTime = Date.now();
    if (this.ticketTimerInterval) clearInterval(this.ticketTimerInterval);
    this.ticketTimerInterval = setInterval(() => this.updateTicketTimer(), 1000);
    this.updateTicketTimer();

    try {
      const response = await Auth.fetchWithAuth('/api/automation/create-ticket', {
        method: 'POST',
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        let errorDetail = `Error HTTP ${response.status}`;
        try {
          const errJson = await response.json();
          if (errJson && errJson.detail) errorDetail = errJson.detail;
        } catch (_) {}
        throw new Error(errorDetail);
      }

      if (!response.body) {
        throw new Error('El navegador no soporta streaming de respuesta.');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // Keep last incomplete line in buffer

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith('data:')) {
            const jsonStr = trimmed.slice(5).trim();
            if (jsonStr) {
              try {
                const eventData = JSON.parse(jsonStr);
                this.handleTicketSSEEvent(eventData, payload);
              } catch (e) {
                console.warn('Error parseando evento SSE:', e, jsonStr);
              }
            }
          }
        }
      }

      // Check any remaining buffer content
      if (buffer.trim().startsWith('data:')) {
        const jsonStr = buffer.trim().slice(5).trim();
        if (jsonStr) {
          try {
            const eventData = JSON.parse(jsonStr);
            this.handleTicketSSEEvent(eventData, payload);
          } catch (_) {}
        }
      }

    } catch (err) {
      this.handleTicketError(err.message || 'Error de conexión durante la ejecución');
    } finally {
      this.setTicketExecutionState(false);
      if (this.ticketTimerInterval) {
        clearInterval(this.ticketTimerInterval);
        this.ticketTimerInterval = null;
      }
    }
  },

  handleTicketSSEEvent(eventData, formData) {
    if (!eventData || !eventData.type) return;

    if (eventData.type === 'log') {
      const level = eventData.level || 'info';
      const message = eventData.message || '';
      this.appendLogEntry(message, level);

      // Estimate progress and update current step according to event message
      const msgLower = message.toLowerCase();
      if (msgLower.includes('iniciando proceso') || msgLower.includes('iniciando navegador')) {
        this.updateTicketProgress(15);
        this.updateTicketStatus('running', 'En ejecución', 'Iniciando navegador Chromium...');
      } else if (msgLower.includes('conectando a portal') || msgLower.includes('autenticando')) {
        this.updateTicketProgress(30);
        this.updateTicketStatus('running', 'En ejecución', 'Autenticando en portal Service Manager...');
      } else if (msgLower.includes('centro de servicios') || msgLower.includes('servicios internos')) {
        this.updateTicketProgress(50);
        this.updateTicketStatus('running', 'En ejecución', 'Navegando a formulario de interacción...');
      } else if (msgLower.includes('ingresando contacto') || msgLower.includes('título') || msgLower.includes('descripción')) {
        this.updateTicketProgress(65);
        this.updateTicketStatus('running', 'En ejecución', 'Llenando datos del formulario...');
      } else if (msgLower.includes('clasificación') || msgLower.includes('área') || msgLower.includes('grupo')) {
        this.updateTicketProgress(80);
        this.updateTicketStatus('running', 'En ejecución', 'Asignando clasificación y grupo...');
      } else if (msgLower.includes('guardando interacción') || msgLower.includes('guardar')) {
        this.updateTicketProgress(90);
        this.updateTicketStatus('running', 'En ejecución', 'Guardando ticket en Service Manager...');
      } else if (msgLower.includes('esperando generación') || msgLower.includes('captura de id')) {
        this.updateTicketProgress(95);
        this.updateTicketStatus('running', 'En ejecución', 'Capturando N° de interacción generado...');
      } else if (msgLower.includes('ticket generado exitosamente') || level === 'success') {
        this.updateTicketProgress(100);
        this.updateTicketStatus('active', 'Completado', '¡Ticket generado exitosamente!');
      } else if (level === 'error') {
        this.updateTicketStatus('error', 'Error', 'Error en la ejecución');
      }
    } else if (eventData.type === 'complete') {
      this.updateTicketProgress(100);
      this.updateTicketStatus('active', 'Completado', '¡Ticket creado exitosamente!');
      const ticketId = eventData.ticket_id || 'SD0000000';
      this.openTicketSuccessModal(ticketId, formData);
    } else if (eventData.type === 'error') {
      const errorMsg = eventData.message || 'Error desconocido en la automatización';
      this.handleTicketError(errorMsg);
    }
  },

  appendLogEntry(message, level = 'info') {
    const consoleEl = document.getElementById('ticket-logs-console');
    if (!consoleEl) return;

    // Hide welcome message on first log
    const welcomeMsg = consoleEl.querySelector('.terminal-welcome-msg');
    if (welcomeMsg && this.ticketLogCount === 0) {
      welcomeMsg.style.display = 'none';
    }

    const now = new Date();
    const timeStr = [
      String(now.getHours()).padStart(2, '0'),
      String(now.getMinutes()).padStart(2, '0'),
      String(now.getSeconds()).padStart(2, '0')
    ].join(':');

    let tagText = 'INFO';
    let tagClass = 'log-tag-info';
    let msgClass = 'log-msg-info';

    switch (level.toLowerCase()) {
      case 'step':
        tagText = 'PASO';
        tagClass = 'log-tag-step';
        msgClass = 'log-msg-step';
        break;
      case 'success':
        tagText = 'ÉXITO';
        tagClass = 'log-tag-success';
        msgClass = 'log-msg-success';
        break;
      case 'warn':
      case 'warning':
        tagText = 'AVISO';
        tagClass = 'log-tag-warn';
        msgClass = 'log-msg-warn';
        break;
      case 'error':
        tagText = 'ERROR';
        tagClass = 'log-tag-error';
        msgClass = 'log-msg-error';
        break;
      default:
        tagText = 'INFO';
        tagClass = 'log-tag-info';
        msgClass = 'log-msg-info';
        break;
    }

    // Format message text: highlight ticket IDs (SD..., IM...)
    let formattedMsg = this.escapeHtml(message);
    formattedMsg = formattedMsg.replace(/\b(SD\d{5,10}|IM\d{5,10})\b/g, '<span class="log-ticket-badge">$1</span>');

    const entryDiv = document.createElement('div');
    entryDiv.className = 'log-entry';
    entryDiv.innerHTML = `
      <span class="log-time">[${timeStr}]</span>
      <span class="log-tag ${tagClass}">${tagText}</span>
      <span class="log-msg ${msgClass}">${formattedMsg}</span>
    `;

    consoleEl.appendChild(entryDiv);

    this.ticketLogCount++;
    this.ticketLogsRaw.push(`[${timeStr}] [${tagText}] ${message}`);

    const counterEl = document.getElementById('ticket-log-counter');
    if (counterEl) {
      counterEl.textContent = `${this.ticketLogCount} ${this.ticketLogCount === 1 ? 'evento' : 'eventos'}`;
    }

    if (this.ticketAutoScroll) {
      consoleEl.scrollTop = consoleEl.scrollHeight;
    }
  },

  handleTicketError(errorMessage) {
    this.appendLogEntry(`Error: ${errorMessage}`, 'error');
    this.updateTicketStatus('error', 'Error', 'Falló la ejecución de la automatización');
  },

  setTicketExecutionState(isRunning) {
    this.isTicketRunning = isRunning;

    const btn = document.getElementById('btn-execute-ticket');
    const spinner = document.getElementById('ticket-spinner');
    const btnIcon = document.getElementById('ticket-btn-icon');
    const btnText = document.getElementById('ticket-btn-text');

    if (btn) btn.disabled = isRunning;
    if (spinner) spinner.style.display = isRunning ? 'inline-block' : 'none';
    if (btnIcon) btnIcon.style.display = isRunning ? 'none' : 'inline';
    if (btnText) btnText.textContent = isRunning ? 'Ejecutando...' : 'Ejecutar';
  },

  updateTicketStatus(state, badgeText, stepText) {
    const badge = document.getElementById('ticket-status-badge');
    const dot = document.getElementById('ticket-status-dot');
    const step = document.getElementById('ticket-current-step');

    if (badge) {
      badge.className = 'badge';
      if (state === 'running') badge.classList.add('badge-info');
      else if (state === 'active' || state === 'success') badge.classList.add('badge-success');
      else if (state === 'error') badge.classList.add('badge-danger');
      else badge.classList.add('badge-neutral');
      
      badge.textContent = badgeText;
    }

    if (dot) {
      dot.className = 'status-indicator-dot';
      if (state === 'running') dot.classList.add('running');
      else if (state === 'active' || state === 'success') dot.classList.add('active');
      else if (state === 'error') dot.classList.add('error');
    }

    if (step && stepText) {
      step.textContent = stepText;
    }
  },

  updateTicketProgress(percent) {
    const bar = document.getElementById('ticket-progress-bar');
    if (bar) {
      const clamped = Math.max(0, Math.min(100, percent));
      bar.style.width = `${clamped}%`;
    }
  },

  updateTicketTimer() {
    if (!this.ticketStartTime) return;
    const elapsedMs = Date.now() - this.ticketStartTime;
    const totalSeconds = Math.floor(elapsedMs / 1000);
    const mins = String(Math.floor(totalSeconds / 60)).padStart(2, '0');
    const secs = String(totalSeconds % 60).padStart(2, '0');
    const timerEl = document.getElementById('ticket-elapsed-time');
    if (timerEl) {
      timerEl.textContent = `⏱️ ${mins}:${secs}`;
    }
  },

  clearTicketLogs() {
    this.ticketLogCount = 0;
    this.ticketLogsRaw = [];

    const consoleEl = document.getElementById('ticket-logs-console');
    if (consoleEl) {
      consoleEl.innerHTML = `
        <div class="terminal-welcome-msg">
          <div class="terminal-line terminal-prompt">$ service-manager-bot --ready</div>
          <div class="terminal-line terminal-hint">Presiona <strong>"🚀 Ejecutar"</strong> para iniciar el flujo automatizado de creación de interacción en Service Manager.</div>
          <div class="terminal-line terminal-hint-sub">Los eventos, diagnósticos y capturas de ID se mostrarán aquí en tiempo real vía Server-Sent Events (SSE).</div>
        </div>
      `;
    }

    const counterEl = document.getElementById('ticket-log-counter');
    if (counterEl) counterEl.textContent = '0 eventos';

    const timerEl = document.getElementById('ticket-elapsed-time');
    if (timerEl) timerEl.textContent = '⏱️ 00:00';

    this.updateTicketProgress(0);
    this.updateTicketStatus('neutral', 'Inactivo', 'Listo para iniciar');
  },

  toggleAutoScroll() {
    this.ticketAutoScroll = !this.ticketAutoScroll;
    const btn = document.getElementById('btn-toggle-autoscroll');
    if (btn) {
      btn.classList.toggle('active', this.ticketAutoScroll);
      btn.textContent = this.ticketAutoScroll ? '📜 Auto-scroll: ON' : '📜 Auto-scroll: OFF';
    }
  },

  async copyConsoleLogs() {
    const btn = document.getElementById('btn-copy-console');
    let textToCopy = '';

    if (this.ticketLogsRaw.length > 0) {
      textToCopy = this.ticketLogsRaw.join('\n');
    } else {
      const consoleEl = document.getElementById('ticket-logs-console');
      textToCopy = consoleEl ? (consoleEl.innerText || consoleEl.textContent || '').trim() : '';
    }

    if (!textToCopy) {
      alert('No hay registros o logs en la consola para copiar.');
      return;
    }

    const ok = await this.copyTextToClipboard(textToCopy);
    if (ok && btn) {
      const originalText = btn.innerHTML;
      btn.innerHTML = '✓ ¡Copiado!';
      btn.classList.add('btn-success');
      setTimeout(() => {
        btn.innerHTML = originalText;
        btn.classList.remove('btn-success');
      }, 2000);
    }
  },

  openTicketSuccessModal(ticketId, formData = {}) {
    const modal = document.getElementById('ticket-success-modal');
    if (!modal) return;

    const idEl = document.getElementById('ticket-success-id');
    if (idEl) idEl.textContent = ticketId || 'SD0000000';

    const contactoEl = document.getElementById('modal-summary-contacto');
    if (contactoEl) contactoEl.textContent = formData.contacto || 'ALEJANDRO JAVIER AGUILAR MORALES';

    const tituloEl = document.getElementById('modal-summary-titulo');
    if (tituloEl) tituloEl.textContent = formData.titulo || 'Creacion test automatizacion';

    const grupoEl = document.getElementById('modal-summary-grupo');
    if (grupoEl) grupoEl.textContent = formData.grupo || 'Lideres Tecnicos';

    const areaEl = document.getElementById('modal-summary-area');
    if (areaEl) {
      const areaStr = [formData.area || 'Proyectos', formData.subarea || 'Apoyo habilitacion cliente'].join(' / ');
      areaEl.textContent = areaStr;
    }

    const feedbackEl = document.getElementById('ticket-copy-feedback');
    if (feedbackEl) feedbackEl.style.display = 'none';

    const copyBtnText = document.getElementById('copy-ticket-btn-text');
    if (copyBtnText) copyBtnText.textContent = '📋 Copiar Ticket';

    modal.style.display = 'flex';
  },

  closeSuccessModal() {
    const modal = document.getElementById('ticket-success-modal');
    if (modal) {
      modal.style.display = 'none';
    }
  },

  async copyTicketIdToClipboard() {
    const idEl = document.getElementById('ticket-success-id');
    const feedbackEl = document.getElementById('ticket-copy-feedback');
    const btnTextEl = document.getElementById('copy-ticket-btn-text');

    const ticketId = idEl ? idEl.textContent.trim() : '';
    if (!ticketId) return;

    const ok = await this.copyTextToClipboard(ticketId);
    if (ok) {
      if (feedbackEl) feedbackEl.style.display = 'block';
      if (btnTextEl) btnTextEl.textContent = '✓ ¡Copiado!';

      setTimeout(() => {
        if (feedbackEl) feedbackEl.style.display = 'none';
        if (btnTextEl) btnTextEl.textContent = '📋 Copiar Ticket';
      }, 2500);
    }
  },

  async copyTextToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (err) {
        console.warn('navigator.clipboard falló, usando fallback textarea:', err);
      }
    }

    try {
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.left = '-999999px';
      textArea.style.top = '-999999px';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      const successful = document.execCommand('copy');
      textArea.remove();
      return successful;
    } catch (err) {
      console.error('Error al copiar al portapapeles con fallback:', err);
      return false;
    }
  },

  // --------------------------------------------------------------------------
  // MÓDULO 4: SOLICITUD LTI
  // --------------------------------------------------------------------------
  async loadSolicitudCatalogos() {
    try {
      const res = await Auth.fetchWithAuth('/api/solicitudes/catalogos');
      const data = await res.json();
      this.solicitudLideresList = data.lideres || [];
      this.solicitudEstadosList = data.estados || ['Generado'];
      this.solicitudTiposServicioList = data.tipos_servicio || ['Otros'];

      // Populate Estados select (Fijo e inmutable en 'Generado')
      const estadoSelect = document.getElementById('solicitud-estado');
      if (estadoSelect) {
        estadoSelect.innerHTML = '<option value="Generado" selected>Generado</option>';
        estadoSelect.value = 'Generado';
        estadoSelect.disabled = true;
      }

      // Populate Tipo de Servicio hidden input
      const tipoInput = document.getElementById('solicitud-tipo-servicio');
      if (tipoInput) {
        tipoInput.value = 'Otros';
      }

      this.solicitudCatalogosLoaded = true;
    } catch (e) {
      console.error('Error al cargar catálogos de solicitud LTI:', e);
    }
  },

  async handleAutocompleteInput(query) {
    const q = (query || '').trim();
    const dropdown = document.getElementById('solicitud-autocomplete-dropdown');
    const spinner = document.getElementById('autocomplete-spinner');
    if (!dropdown) return;

    if (q.length < 2) {
      this.hideAutocompleteDropdown();
      if (spinner) spinner.style.display = 'none';
      return;
    }

    if (spinner) spinner.style.display = 'inline-block';

    try {
      const res = await Auth.fetchWithAuth(`/api/solicitudes/autocomplete-proyectos?q=${encodeURIComponent(q)}`);
      const results = await res.json();
      this.autocompleteResults = results || [];
      this.autocompleteSelectedIdx = -1;
      this.renderAutocompleteDropdown(this.autocompleteResults);
    } catch (e) {
      console.warn('Error en autocompletado:', e);
      this.hideAutocompleteDropdown();
    } finally {
      if (spinner) spinner.style.display = 'none';
    }
  },

  renderAutocompleteDropdown(results) {
    const dropdown = document.getElementById('solicitud-autocomplete-dropdown');
    if (!dropdown) return;

    if (!results || results.length === 0) {
      dropdown.innerHTML = `
        <div class="autocomplete-empty">
          No se encontraron proyectos en SGA Backlog.<br>
          <small style="color: var(--text-muted);">Puedes continuar ingresando los datos de forma manual.</small>
        </div>
      `;
      dropdown.style.display = 'block';
      return;
    }

    dropdown.innerHTML = results.map((item, idx) => {
      const projNum = item.nro_proyecto || item.numero_proyecto_limpio || '';
      const clientName = item.cliente || 'Cliente sin nombre';
      const solicitante = item.solicitante ? ` • Solicitante: ${item.solicitante}` : '';
      const rut = item.rut_cliente ? ` [RUT: ${item.rut_cliente}]` : '';

      return `
        <div class="autocomplete-item" data-index="${idx}" onclick="App.selectAutocompleteItem(${idx})">
          <div class="autocomplete-item-header">
            <span class="autocomplete-item-proj">${this.escapeHtml(projNum)}</span>
            <span class="autocomplete-item-client">${this.escapeHtml(clientName)}</span>
          </div>
          <div class="autocomplete-item-sub">
            ${this.escapeHtml(rut)}${this.escapeHtml(solicitante)}
          </div>
        </div>
      `;
    }).join('');

    dropdown.style.display = 'block';
  },

  selectAutocompleteItem(index) {
    const item = this.autocompleteResults[index];
    if (!item) return;

    const projInput = document.getElementById('solicitud-nro-proyecto');
    const clienteInput = document.getElementById('solicitud-cliente');
    const detalleInput = document.getElementById('solicitud-detalle');
    const solotsBadge = document.getElementById('detalle-solots-badge');

    if (projInput) {
      projInput.value = item.nro_proyecto || item.numero_proyecto_limpio || '';
      projInput.classList.remove('is-invalid');
    }

    if (clienteInput && item.cliente) {
      clienteInput.value = item.cliente;
      clienteInput.classList.remove('is-invalid');
    }

    // Prellenar Detalle con Solots Liray si vienen en el item o consultarlos
    if (item.detalle_sugerido) {
      if (detalleInput) {
        detalleInput.value = item.detalle_sugerido;
        detalleInput.classList.remove('is-invalid');
        this.lastLoadedSolotsText = item.detalle_sugerido;
      }
      if (solotsBadge) solotsBadge.style.display = 'inline-flex';
    } else if (item.has_solots_liray === false) {
      if (solotsBadge) solotsBadge.style.display = 'none';
      if (detalleInput && (this.lastLoadedSolotsText && detalleInput.value.trim() === this.lastLoadedSolotsText.trim())) {
        detalleInput.value = '';
        this.lastLoadedSolotsText = '';
      }
    } else {
      // Si no venía precalculado, consultar el endpoint específico
      const projNum = item.nro_proyecto || item.numero_proyecto_limpio;
      if (projNum) {
        this.fetchAndFillSolotsLiray(projNum, true);
      }
    }

    this.hideAutocompleteDropdown();
  },

  async fetchAndFillSolotsLiray(nroProyecto, force = false) {
    if (!nroProyecto || String(nroProyecto).trim().length < 2) return;
    const detalleInput = document.getElementById('solicitud-detalle');
    const solotsBadge = document.getElementById('detalle-solots-badge');

    try {
      const res = await Auth.fetchWithAuth(`/api/solicitudes/solots-liray?nro_proyecto=${encodeURIComponent(nroProyecto)}`);
      if (res.ok) {
        const data = await res.json();
        const text = data.formatted_text || data.detalle_sugerido || '';
        if (detalleInput) {
          const currentVal = (detalleInput.value || '').trim();
          const isUnmodifiedPreviousSolots = this.lastLoadedSolotsText && currentVal === this.lastLoadedSolotsText.trim();
          const isEmpty = !currentVal;

          if (text) {
            if (force || isEmpty || isUnmodifiedPreviousSolots) {
              detalleInput.value = text;
              detalleInput.classList.remove('is-invalid');
              this.lastLoadedSolotsText = text;
              if (solotsBadge) solotsBadge.style.display = 'inline-flex';
            }
          } else {
            if (solotsBadge) solotsBadge.style.display = 'none';
            if (isUnmodifiedPreviousSolots) {
              detalleInput.value = '';
              this.lastLoadedSolotsText = '';
            }
          }
        }
      }
    } catch (e) {
      console.warn('Error al obtener solots liray:', e);
    }
  },

  handleAutocompleteKeydown(e) {
    const dropdown = document.getElementById('solicitud-autocomplete-dropdown');
    if (!dropdown || dropdown.style.display === 'none' || !this.autocompleteResults.length) {
      return;
    }

    const items = dropdown.querySelectorAll('.autocomplete-item');
    if (!items.length) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (this.autocompleteSelectedIdx < items.length - 1) {
        this.autocompleteSelectedIdx++;
      } else {
        this.autocompleteSelectedIdx = 0;
      }
      this.updateAutocompleteHighlight(items);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (this.autocompleteSelectedIdx > 0) {
        this.autocompleteSelectedIdx--;
      } else {
        this.autocompleteSelectedIdx = items.length - 1;
      }
      this.updateAutocompleteHighlight(items);
    } else if (e.key === 'Enter') {
      if (this.autocompleteSelectedIdx >= 0 && this.autocompleteSelectedIdx < this.autocompleteResults.length) {
        e.preventDefault();
        this.selectAutocompleteItem(this.autocompleteSelectedIdx);
      }
    } else if (e.key === 'Escape') {
      this.hideAutocompleteDropdown();
    }
  },

  updateAutocompleteHighlight(items) {
    items.forEach((item, idx) => {
      if (idx === this.autocompleteSelectedIdx) {
        item.classList.add('selected');
        item.scrollIntoView({ block: 'nearest' });
      } else {
        item.classList.remove('selected');
      }
    });
  },

  hideAutocompleteDropdown() {
    const dropdown = document.getElementById('solicitud-autocomplete-dropdown');
    if (dropdown) {
      dropdown.style.display = 'none';
      dropdown.innerHTML = '';
    }
    this.autocompleteSelectedIdx = -1;
  },

  async submitSolicitudForm() {
    if (this.isSolicitudSubmitting) return;

    const projInput = document.getElementById('solicitud-nro-proyecto');
    const clienteInput = document.getElementById('solicitud-cliente');
    const estadoSelect = document.getElementById('solicitud-estado');
    const fechaInput = document.getElementById('solicitud-fecha');
    const tipoSelect = document.getElementById('solicitud-tipo-servicio');
    const detalleInput = document.getElementById('solicitud-detalle');

    const numero_proyecto = (projInput?.value || '').trim();
    const cliente = (clienteInput?.value || '').trim();
    const estado = 'Generado';
    const fecha_solicitud = (fechaInput?.value || '').trim();
    const tipo_servicio = (tipoSelect?.value || 'Otros').trim();
    const detalle = (detalleInput?.value || '').trim();

    // Reset error visuals
    const dupAlert = document.getElementById('solicitud-duplicate-alert');
    const errAlert = document.getElementById('solicitud-error-alert');
    const errDesc = document.getElementById('solicitud-error-desc');
    if (dupAlert) dupAlert.style.display = 'none';
    if (errAlert) errAlert.style.display = 'none';

    let hasErrors = false;
    let firstInvalid = null;

    const validateField = (el, val) => {
      if (!val) {
        if (el) el.classList.add('is-invalid');
        hasErrors = true;
        if (!firstInvalid && el) firstInvalid = el;
      } else if (el) {
        el.classList.remove('is-invalid');
      }
    };

    validateField(projInput, numero_proyecto);
    validateField(clienteInput, cliente);
    validateField(estadoSelect, estado);
    validateField(fechaInput, fecha_solicitud);
    validateField(detalleInput, detalle);

    if (hasErrors) {
      if (errAlert && errDesc) {
        errDesc.textContent = 'Por favor completa todos los campos requeridos con asterisco (*) antes de solicitar.';
        errAlert.style.display = 'flex';
        errAlert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
      if (firstInvalid) {
        firstInvalid.focus();
      }
      return;
    }

    // Set loading state
    this.isSolicitudSubmitting = true;
    const submitBtn = document.getElementById('btn-submit-solicitud');
    const spinner = document.getElementById('solicitud-spinner');
    const btnIcon = document.getElementById('solicitud-btn-icon');
    const btnText = document.getElementById('solicitud-btn-text');

    if (submitBtn) submitBtn.disabled = true;
    if (spinner) spinner.style.display = 'inline-block';
    if (btnIcon) btnIcon.style.display = 'none';
    if (btnText) btnText.textContent = 'Guardando solicitud...';

    try {
      const response = await Auth.fetchWithAuth('/api/solicitudes/crear', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cliente,
          numero_proyecto,
          lt_asignado: null,
          estado: 'Generado',
          fecha_solicitud,
          detalle,
          tipo_servicio
        })
      });

      if (response.status === 409) {
        const errorData = await response.json();
        const existing = errorData.existing || {};
        this.duplicateProjectId = existing.ID || null;

        if (dupAlert) {
          const titleEl = document.getElementById('duplicate-alert-title');
          const descEl = document.getElementById('duplicate-alert-desc');
          if (titleEl) {
            titleEl.textContent = `⚠️ El N° de proyecto ${numero_proyecto} ya existe en el sistema`;
          }
          if (descEl) {
            const safeId = this.escapeHtml(existing.ID || '-');
            const safeLt = this.escapeHtml(existing.LT_Asignado || 'Sin Asignar');
            const safeEstado = this.escapeHtml(existing.Estado || '-');
            descEl.innerHTML = `
              Este proyecto ya se encuentra registrado con ID <strong>#${safeId}</strong> asignado a <strong>${safeLt}</strong> en estado <strong>${safeEstado}</strong>.<br>
              <strong>Sugerencia:</strong> Si necesitas agregar más servicios, configuraciones o alcances, edita el campo <em>"Detalle"</em> o complementa el proyecto existente desde el módulo de Seguimiento.
            `;
          }
          dupAlert.style.display = 'flex';
          dupAlert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      } else if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const msg = errorData.detail || errorData.message || 'Ocurrió un error al guardar la solicitud en la base de datos.';
        if (errAlert && errDesc) {
          errDesc.textContent = msg;
          errAlert.style.display = 'flex';
          errAlert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      } else {
        const resData = await response.json();
        const created = resData.data || {};
        this.openSolicitudSuccessModal(created);
      }
    } catch (e) {
      if (errAlert && errDesc) {
        errDesc.textContent = `Error de conexión o comunicación con el servidor: ${e.message}`;
        errAlert.style.display = 'flex';
        errAlert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    } finally {
      this.isSolicitudSubmitting = false;
      if (submitBtn) submitBtn.disabled = false;
      if (spinner) spinner.style.display = 'none';
      if (btnIcon) btnIcon.style.display = 'inline';
      if (btnText) btnText.textContent = 'Solicitar';
    }
  },

  openSolicitudSuccessModal(created) {
    const modal = document.getElementById('solicitud-success-modal');
    if (!modal) return;

    const idEl = document.getElementById('solicitud-success-id');
    const clienteEl = document.getElementById('modal-solicitud-cliente');
    const nroEl = document.getElementById('modal-solicitud-nro');
    const ltEl = document.getElementById('modal-solicitud-lt');
    const estadoEl = document.getElementById('modal-solicitud-estado');
    const fechaEl = document.getElementById('modal-solicitud-fecha');

    if (idEl) idEl.textContent = created.ID || '0';
    if (clienteEl) clienteEl.textContent = created.Cliente || '-';
    if (nroEl) nroEl.textContent = this.formatNumeroProyecto(created.Numero_Proyecto);
    if (ltEl) ltEl.textContent = created.LT_Asignado || 'Sin Asignar';
    if (estadoEl) estadoEl.innerHTML = this.renderStatusBadge(created.Estado);
    if (fechaEl) fechaEl.textContent = this.formatDateDMY(created.Creado);

    modal.style.display = 'flex';
  },

  closeSolicitudModal() {
    const modal = document.getElementById('solicitud-success-modal');
    if (modal) {
      modal.style.display = 'none';
    }
  },

  resetSolicitudForm() {
    const projInput = document.getElementById('solicitud-nro-proyecto');
    const clienteInput = document.getElementById('solicitud-cliente');
    const estadoSelect = document.getElementById('solicitud-estado');
    const fechaInput = document.getElementById('solicitud-fecha');
    const tipoSelect = document.getElementById('solicitud-tipo-servicio');
    const detalleInput = document.getElementById('solicitud-detalle');
    const solotsBadge = document.getElementById('detalle-solots-badge');

    if (projInput) {
      projInput.value = '';
      projInput.classList.remove('is-invalid');
    }
    if (clienteInput) {
      clienteInput.value = '';
      clienteInput.classList.remove('is-invalid');
    }
    if (detalleInput) {
      detalleInput.value = '';
      detalleInput.classList.remove('is-invalid');
    }
    if (solotsBadge) {
      solotsBadge.style.display = 'none';
    }
    this.lastLoadedSolotsText = '';

    if (estadoSelect) {
      estadoSelect.innerHTML = '<option value="Generado" selected>Generado</option>';
      estadoSelect.value = 'Generado';
      estadoSelect.disabled = true;
      estadoSelect.classList.remove('is-invalid');
    }

    if (tipoSelect) {
      tipoSelect.value = 'Otros';
    }

    if (fechaInput) {
      const today = new Date();
      const year = today.getFullYear();
      const month = String(today.getMonth() + 1).padStart(2, '0');
      const day = String(today.getDate()).padStart(2, '0');
      fechaInput.value = `${year}-${month}-${day}`;
      fechaInput.classList.remove('is-invalid');
    }

    const dupAlert = document.getElementById('solicitud-duplicate-alert');
    const errAlert = document.getElementById('solicitud-error-alert');
    if (dupAlert) dupAlert.style.display = 'none';
    if (errAlert) errAlert.style.display = 'none';
    this.duplicateProjectId = null;
    this.hideAutocompleteDropdown();
  },

  // --------------------------------------------------------------------------
  // HELPERS
  // --------------------------------------------------------------------------
  formatNumeroProyecto(num) {
    if (num === null || num === undefined) return 'N/A';
    const str = String(num).trim();
    if (!str || str === 'N/A' || str === '-' || str.toUpperCase() === 'NONE' || str.toUpperCase() === 'NULL') return 'N/A';
    if (str.startsWith('000')) return str;
    return '000' + str;
  },

  formatSolicitante(name) {
    const UNMATCHED = 'NO IDENTIFICADO. PROYECTO DEMO O NO HA LLEGADO PROYECTO A INSTALACIONES';
    if (name === null || name === undefined) return UNMATCHED;
    const str = String(name).trim();
    if (!str || str === 'N/A' || str === '-' || str.toUpperCase() === 'NONE' || str.toUpperCase() === 'NULL') {
      return UNMATCHED;
    }
    if (str.startsWith('NO IDENTIFICADO')) {
      return UNMATCHED;
    }
    // Remove Corp... prefix (e.g. Corp1-, Corp2-, Corp -, Corp1 -)
    const cleaned = str.replace(/^Corp[0-9]*\s*[-–—:]*\s*/i, '').trim();
    return cleaned ? cleaned.toUpperCase() : UNMATCHED;
  },

  formatDateDMY(dateStr) {
    if (!dateStr) return 'N/A';
    try {
      const cleanStr = String(dateStr).trim().split(' ')[0]; // Takes YYYY-MM-DD part
      if (/^\d{4}-\d{2}-\d{2}$/.test(cleanStr)) {
        const [year, month, day] = cleanStr.split('-');
        return `${day}-${month}-${year}`;
      }
      if (cleanStr === 'None' || cleanStr === 'null' || cleanStr === '-') return 'N/A';
      return cleanStr;
    } catch {
      return String(dateStr);
    }
  },

  renderStatusBadge(status) {
    if (status === null || status === undefined || String(status).trim() === '') {
      return `<span class="badge badge-neutral">Desconocido</span>`;
    }
    const raw = String(status).trim();
    const s = raw.toLowerCase();
    
    if (s.includes('atendido') || s.includes('cerrado') || s.includes('completado') || s.includes('ejecutada') || s.includes('closed')) {
      return `<span class="badge badge-success">✓ ${this.escapeHtml(raw)}</span>`;
    } else if (s.includes('generado') || s.includes('en ejecucion') || s.includes('en curso') || s.includes('en revision') || s.includes('en revisión')) {
      return `<span class="badge badge-info">🚀 ${this.escapeHtml(raw)}</span>`;
    } else if (s.includes('pendiente') || s.includes('asignad') || s.includes('progreso') || s.includes('open') || s.includes('in progress')) {
      return `<span class="badge badge-warning">⏳ ${this.escapeHtml(raw)}</span>`;
    } else if (s.includes('cancelad') || s.includes('rechazad') || s.includes('abortad') || s.includes('eliminad')) {
      return `<span class="badge badge-danger">✕ ${this.escapeHtml(raw)}</span>`;
    }
    return `<span class="badge badge-info">${this.escapeHtml(raw)}</span>`;
  },

  escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  },

  exportCurrentTableToCSV() {
    if (this.currentProject) {
      alert('Exportando detalle del proyecto actual a CSV...');
    } else {
      if (!this.projectsData || this.projectsData.length === 0) return;
      const headers = ['Cliente', 'N_Proyecto', 'LT_Asignado', 'Solicitante', 'Estado', 'Fecha_Solicitud_LTI', 'Detalle'];
      const rows = this.projectsData.map(p => [
        `"${(p.Cliente || '').replace(/"/g, '""')}"`,
        `"${(this.formatNumeroProyecto(p.Numero_Proyecto) || '').replace(/"/g, '""')}"`,
        `"${(p.LT_Asignado || '').replace(/"/g, '""')}"`,
        `"${(this.formatSolicitante(p.Solicitante) || '').replace(/"/g, '""')}"`,
        `"${(p.Estado || '').replace(/"/g, '""')}"`,
        `"${this.formatDateDMY(p.Creado)}"`,
        `"${(p.Detalle || '').replace(/"/g, '""')}"`
      ]);

      const csvContent = '\uFEFF' + [headers.join(';'), ...rows.map(r => r.join(';'))].join('\n');
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.setAttribute('href', url);
      link.setAttribute('download', `Proyectos_LTI_${new Date().toISOString().slice(0, 10)}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  },

  // --------------------------------------------------------------------------
  // EDICIÓN Y ELIMINACIÓN DE PROYECTOS (MODALES Y ACCIONES)
  // --------------------------------------------------------------------------
  async openEditProjectModal(projectId) {
    try {
      const res = await Auth.fetchWithAuth(`/api/proyectos/${projectId}`);
      if (!res.ok) throw new Error('No se pudo obtener la información del proyecto');
      const project = await res.json();

      // Llenar campos del modal
      const idInput = document.getElementById('edit-project-id');
      const nroInput = document.getElementById('edit-project-nro');
      const fechaInput = document.getElementById('edit-project-fecha');
      const clienteInput = document.getElementById('edit-project-cliente');
      const detalleInput = document.getElementById('edit-project-detalle');
      const comentarioInput = document.getElementById('edit-project-comentario');

      if (idInput) idInput.value = project.ID;
      if (nroInput) nroInput.value = this.formatNumeroProyecto(project.Numero_Proyecto);
      if (fechaInput) fechaInput.value = this.formatDateDMY(project.Creado);
      if (clienteInput) clienteInput.value = project.Cliente || '';
      if (detalleInput) detalleInput.value = project.Detalle || '';
      if (comentarioInput) comentarioInput.value = project.Comentario || '';
      
      // Poblar select de líderes
      const ltSelect = document.getElementById('edit-project-lt-asignado');
      if (ltSelect) {
        ltSelect.innerHTML = '<option value="">— Sin Asignar —</option>';
        if (this.lideresList && this.lideresList.length > 0) {
          this.lideresList.forEach(lt => {
            const opt = document.createElement('option');
            opt.value = lt;
            opt.textContent = lt;
            if (project.LT_Asignado === lt) opt.selected = true;
            ltSelect.appendChild(opt);
          });
        }
      }

      // Seleccionar Estado
      const estadoSelect = document.getElementById('edit-project-estado');
      if (estadoSelect) {
        estadoSelect.value = project.Estado || 'Generado';
      }

      // Seleccionar Tipo de Servicio
      const tipoSelect = document.getElementById('edit-project-tipo-servicio');
      if (tipoSelect) {
        tipoSelect.value = project.Tipo_Servicio || 'Otros';
      }

      // Ocultar banner de error previo
      const errAlert = document.getElementById('edit-project-error-alert');
      if (errAlert) errAlert.style.display = 'none';

      // Mostrar modal
      const modal = document.getElementById('edit-project-modal');
      if (modal) modal.style.display = 'flex';
    } catch (err) {
      this.showToast(`Error: ${err.message}`, 'danger');
    }
  },

  closeEditProjectModal() {
    const modal = document.getElementById('edit-project-modal');
    if (modal) modal.style.display = 'none';
  },

  async submitEditProjectForm() {
    const projectId = document.getElementById('edit-project-id')?.value;
    const cliente = document.getElementById('edit-project-cliente')?.value.trim() || '';
    const ltAsignado = document.getElementById('edit-project-lt-asignado')?.value || '';
    const estado = document.getElementById('edit-project-estado')?.value || '';
    const tipoServicio = document.getElementById('edit-project-tipo-servicio')?.value || 'Otros';
    const detalle = document.getElementById('edit-project-detalle')?.value.trim() || '';
    const comentario = document.getElementById('edit-project-comentario')?.value.trim() || '';
    const errAlert = document.getElementById('edit-project-error-alert');
    const errDesc = document.getElementById('edit-project-error-desc');
    const btn = document.getElementById('btn-save-edit-modal');
    const spinner = document.getElementById('edit-modal-spinner');

    if (!cliente || !estado || !detalle) {
      if (errAlert) errAlert.style.display = 'flex';
      if (errDesc) errDesc.textContent = 'Cliente, Estado y Detalle son obligatorios.';
      return;
    }

    if (errAlert) errAlert.style.display = 'none';
    if (btn) btn.disabled = true;
    if (spinner) spinner.style.display = 'inline-block';

    try {
      const res = await Auth.fetchWithAuth(`/api/proyectos/${projectId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cliente: cliente,
          lt_asignado: ltAsignado || null,
          estado: estado,
          tipo_servicio: tipoServicio || 'Otros',
          detalle: detalle,
          comentario: comentario || null
        })
      });

      const result = await res.json();
      if (!res.ok) {
        throw new Error(result.detail || result.message || 'Error al guardar modificaciones');
      }

      this.closeEditProjectModal();
      this.showToast('Proyecto actualizado exitosamente', 'success');

      // Sincronización Reactiva
      await Promise.all([
        this.loadProjects(),
        this.loadKPIs()
      ]);

      // Si está en Drill Down, refrescar vista en vivo
      if (this.currentProject && this.currentProject.ID == projectId) {
        this.currentProject = result.data;
        const clientTitle = document.getElementById('dd-client-title');
        const ltAssigned = document.getElementById('dd-lt-assigned');
        const ddStatus = document.getElementById('dd-status');
        if (clientTitle) clientTitle.textContent = result.data.Cliente || 'Sin Título';
        if (ltAssigned) ltAssigned.textContent = result.data.LT_Asignado || 'No asignado';
        if (ddStatus) ddStatus.innerHTML = this.renderStatusBadge(result.data.Estado);
        this.renderSummaryTab(result.data);
      }
    } catch (err) {
      if (errAlert) errAlert.style.display = 'flex';
      if (errDesc) errDesc.textContent = err.message;
    } finally {
      if (btn) btn.disabled = false;
      if (spinner) spinner.style.display = 'none';
    }
  },

  async openDeleteProjectModal(projectId) {
    try {
      const res = await Auth.fetchWithAuth(`/api/proyectos/${projectId}`);
      if (!res.ok) throw new Error('No se encontró el proyecto a eliminar');
      const project = await res.json();

      const idInput = document.getElementById('delete-project-id');
      const nroEl = document.getElementById('modal-delete-nro');
      const clienteEl = document.getElementById('modal-delete-cliente');
      const ltEl = document.getElementById('modal-delete-lt');
      const estadoEl = document.getElementById('modal-delete-estado');

      if (idInput) idInput.value = project.ID;
      if (nroEl) nroEl.textContent = this.formatNumeroProyecto(project.Numero_Proyecto);
      if (clienteEl) clienteEl.textContent = project.Cliente || 'Sin título';
      if (ltEl) ltEl.textContent = project.LT_Asignado || 'Sin Asignar';
      if (estadoEl) estadoEl.innerHTML = this.renderStatusBadge(project.Estado);

      const modal = document.getElementById('delete-project-modal');
      if (modal) modal.style.display = 'flex';
    } catch (err) {
      this.showToast(`Error: ${err.message}`, 'danger');
    }
  },

  closeDeleteProjectModal() {
    const modal = document.getElementById('delete-project-modal');
    if (modal) modal.style.display = 'none';
  },

  async confirmDeleteProject() {
    const projectId = document.getElementById('delete-project-id')?.value;
    const btn = document.getElementById('btn-confirm-delete-modal');
    const spinner = document.getElementById('delete-modal-spinner');

    if (btn) btn.disabled = true;
    if (spinner) spinner.style.display = 'inline-block';

    try {
      const res = await Auth.fetchWithAuth(`/api/proyectos/${projectId}`, {
        method: 'DELETE'
      });

      const result = await res.json();
      if (!res.ok) {
        throw new Error(result.detail || result.message || 'Error al eliminar el proyecto');
      }

      this.closeDeleteProjectModal();
      this.showToast('Proyecto eliminado exitosamente', 'success');

      // Si estaba en Drill Down del proyecto eliminado, volver al listado
      if (this.currentProject && this.currentProject.ID == projectId) {
        this.showProjectsList();
      }

      // Sincronización reactiva
      await Promise.all([
        this.loadProjects(),
        this.loadKPIs()
      ]);
    } catch (err) {
      this.showToast(`Error al eliminar: ${err.message}`, 'danger');
    } finally {
      if (btn) btn.disabled = false;
      if (spinner) spinner.style.display = 'none';
    }
  },

  // --------------------------------------------------------------------------
  // COMPONENTE TOAST UNIVERSAL
  // --------------------------------------------------------------------------
  showToast(message, type = 'info') {
    const existing = document.querySelector('.alert-toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'alert-toast';
    const icon = type === 'success' ? '✅' : (type === 'danger' || type === 'error' ? '❌' : (type === 'warning' ? '⚠️' : 'ℹ️'));
    toast.innerHTML = `
      <span style="font-size: 1.2rem;">${icon}</span>
      <span style="font-weight: 500; font-size: 0.9rem;">${this.escapeHtml(message)}</span>
    `;
    const container = document.getElementById('toast-container');
    if (container) {
      container.appendChild(toast);
    } else {
      document.body.appendChild(toast);
    }

    setTimeout(() => {
      toast.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(20px)';
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  }
};

// Start application upon DOM load
document.addEventListener('DOMContentLoaded', () => App.init());
