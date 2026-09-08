/**
 * Main Application Script for App LTI
 */

const CANONICAL_ESTADOS_SHAREPOINT = ['Generado', 'En revision', 'Atendido'];

const App = {
  currentProject: null,
  projectsData: [],
  lideresList: [],
  estadosSharepoint: [],
  activeTab: 'summary',
  activeDirectSearchTab: 'proyectos',
  currentModule: 'projects', // 'projects' | 'direct-search' | 'tickets' | 'solicitud-lti' | 'usuarios'
  searchTags: [], // Tags array for direct search module
  isTicketRunning: false,
  ticketLogCount: 0,
  ticketTimerInterval: null,
  ticketStartTime: null,
  ticketAutoScroll: true,
  ticketLogsRaw: [],
  lastGeneratedTicketId: null,
  lastGeneratedPeticionId: null,
  lastTicketFormData: null,
  selectedEmailFile: null,
  isEmailSending: false,
  solicitudCatalogosLoaded: false,
  solicitudLideresList: [],
  solicitudEstadosList: [],
  solicitudTiposServicioList: [],
  autocompleteResults: [],
  autocompleteSelectedIdx: -1,
  duplicateProjectId: null,
  isSolicitudSubmitting: false,
  lastLoadedSolotsText: '',
  usuariosData: [],
  isUserSubmitting: false,
  userToDeleteId: null,

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
    const navUsuariosBtn = document.getElementById('nav-btn-usuarios');
    if (navUsuariosBtn) {
      navUsuariosBtn.addEventListener('click', () => this.switchModule('usuarios'));
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
          await this.loadInitialData();
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
        if (e.key === 'Enter' || e.key === ' ' || e.code === 'Space') {
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

    const copyPeticionIdBtn = document.getElementById('btn-copy-peticion-id');
    if (copyPeticionIdBtn) {
      copyPeticionIdBtn.addEventListener('click', () => this.copyPeticionIdToClipboard());
    }

    const copyBothIdsBtn = document.getElementById('btn-copy-both-ids');
    if (copyBothIdsBtn) {
      copyBothIdsBtn.addEventListener('click', () => this.copyBothIdsToClipboard());
    }

    // Email Notification Modal Events
    const openEmailBtn = document.getElementById('btn-open-email-modal');
    if (openEmailBtn) {
      openEmailBtn.addEventListener('click', () => this.openEmailTicketModal());
    }

    const closeEmailIcon = document.getElementById('btn-close-email-modal-icon');
    if (closeEmailIcon) {
      closeEmailIcon.addEventListener('click', () => this.closeEmailTicketModal());
    }

    const cancelEmailBtn = document.getElementById('btn-cancel-email') || document.getElementById('btn-cancel-email-modal');
    if (cancelEmailBtn) {
      cancelEmailBtn.addEventListener('click', () => this.closeEmailTicketModal());
    }

    const sendEmailBtn = document.getElementById('btn-send-email') || document.getElementById('btn-send-email-submit');
    if (sendEmailBtn) {
      sendEmailBtn.addEventListener('click', () => this.submitSendTicketEmail());
    }

    const emailForm = document.getElementById('email-ticket-form');
    if (emailForm) {
      emailForm.addEventListener('submit', (e) => {
        e.preventDefault();
        this.submitSendTicketEmail();
      });
    }

    const emailModal = document.getElementById('email-ticket-modal');
    if (emailModal) {
      emailModal.addEventListener('click', (e) => {
        if (e.target === emailModal) {
          this.closeEmailTicketModal();
        }
      });
    }

    const fileDropzone = document.getElementById('file-attachment-dropzone');
    const fileInput = document.getElementById('email-adjunto') || document.getElementById('email-attachment');
    if (fileDropzone && fileInput) {
      fileDropzone.addEventListener('click', (e) => {
        if (e.target.closest('#btn-remove-attachment')) return;
        fileInput.click();
      });

      fileDropzone.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          if (e.target.closest('#btn-remove-attachment')) return;
          e.preventDefault();
          fileInput.click();
        }
      });

      fileInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files[0]) {
          this.handleEmailFileSelect(e.target.files[0]);
        }
      });

      fileDropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.stopPropagation();
        fileDropzone.classList.add('dragover');
      });

      fileDropzone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        e.stopPropagation();
        fileDropzone.classList.remove('dragover');
      });

      fileDropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        fileDropzone.classList.remove('dragover');
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
          this.handleEmailFileSelect(e.dataTransfer.files[0]);
        }
      });
    }

    const removeAttBtn = document.getElementById('btn-remove-attachment');
    if (removeAttBtn) {
      removeAttBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.clearEmailAttachment();
      });
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

    // --- User Management Events (Module 5) ---
    const userSearchInput = document.getElementById('usuarios-search-input');
    if (userSearchInput) {
      const debouncedLoadUsers = this.debounce(() => this.loadUsuarios(), 300);
      userSearchInput.addEventListener('input', () => debouncedLoadUsers());
    }

    const userFilterRol = document.getElementById('usuarios-filter-rol');
    if (userFilterRol) {
      userFilterRol.addEventListener('change', () => this.loadUsuarios());
    }

    const userFilterEstado = document.getElementById('usuarios-filter-estado');
    if (userFilterEstado) {
      userFilterEstado.addEventListener('change', () => this.loadUsuarios());
    }

    const btnResetUserFilters = document.getElementById('btn-usuarios-reset-filters');
    if (btnResetUserFilters) {
      btnResetUserFilters.addEventListener('click', () => {
        if (userSearchInput) userSearchInput.value = '';
        if (userFilterRol) userFilterRol.value = '';
        if (userFilterEstado) userFilterEstado.value = '';
        this.loadUsuarios();
      });
    }

    const btnCreateUserOpen = document.getElementById('btn-create-user-open');
    if (btnCreateUserOpen) {
      btnCreateUserOpen.addEventListener('click', () => this.openCreateUserModal());
    }

    // Create User Modal
    const btnCloseCreateUserIcon = document.getElementById('btn-close-create-user-modal-icon');
    if (btnCloseCreateUserIcon) {
      btnCloseCreateUserIcon.addEventListener('click', () => this.closeCreateUserModal());
    }
    const btnCancelCreateUser = document.getElementById('btn-cancel-create-user-modal');
    if (btnCancelCreateUser) {
      btnCancelCreateUser.addEventListener('click', () => this.closeCreateUserModal());
    }
    const btnSaveCreateUser = document.getElementById('btn-save-create-user-modal');
    if (btnSaveCreateUser) {
      btnSaveCreateUser.addEventListener('click', () => this.submitCreateUserForm());
    }
    const createUserModal = document.getElementById('create-user-modal');
    if (createUserModal) {
      createUserModal.addEventListener('click', (e) => {
        if (e.target === createUserModal) this.closeCreateUserModal();
      });
    }

    // Edit User Modal
    const btnCloseEditUserIcon = document.getElementById('btn-close-edit-user-modal-icon');
    if (btnCloseEditUserIcon) {
      btnCloseEditUserIcon.addEventListener('click', () => this.closeEditUserModal());
    }
    const btnCancelEditUser = document.getElementById('btn-cancel-edit-user-modal');
    if (btnCancelEditUser) {
      btnCancelEditUser.addEventListener('click', () => this.closeEditUserModal());
    }
    const btnSaveEditUser = document.getElementById('btn-save-edit-user-modal');
    if (btnSaveEditUser) {
      btnSaveEditUser.addEventListener('click', () => this.submitEditUserForm());
    }
    const editUserModal = document.getElementById('edit-user-modal');
    if (editUserModal) {
      editUserModal.addEventListener('click', (e) => {
        if (e.target === editUserModal) this.closeEditUserModal();
      });
    }

    // Reset User Password Modal
    const btnCloseResetUserIcon = document.getElementById('btn-close-reset-user-modal-icon');
    if (btnCloseResetUserIcon) {
      btnCloseResetUserIcon.addEventListener('click', () => this.closeResetUserPasswordModal());
    }
    const btnCancelResetUser = document.getElementById('btn-cancel-reset-user-modal');
    if (btnCancelResetUser) {
      btnCancelResetUser.addEventListener('click', () => this.closeResetUserPasswordModal());
    }
    const btnConfirmResetUser = document.getElementById('btn-confirm-reset-user-modal');
    if (btnConfirmResetUser) {
      btnConfirmResetUser.addEventListener('click', () => this.submitResetUserPasswordForm());
    }
    const btnResetDefaultPass = document.getElementById('btn-reset-user-default-pass');
    if (btnResetDefaultPass) {
      btnResetDefaultPass.addEventListener('click', () => {
        const passInput = document.getElementById('reset-user-new-password');
        if (passInput) passInput.value = 'Lti2026!';
      });
    }
    const resetUserModal = document.getElementById('reset-user-password-modal');
    if (resetUserModal) {
      resetUserModal.addEventListener('click', (e) => {
        if (e.target === resetUserModal) this.closeResetUserPasswordModal();
      });
    }

    // Delete User Modal
    const btnCloseDeleteUserIcon = document.getElementById('btn-close-delete-user-modal-icon');
    if (btnCloseDeleteUserIcon) {
      btnCloseDeleteUserIcon.addEventListener('click', () => this.closeDeleteUserModal());
    }
    const btnCancelDeleteUser = document.getElementById('btn-cancel-delete-user-modal');
    if (btnCancelDeleteUser) {
      btnCancelDeleteUser.addEventListener('click', () => this.closeDeleteUserModal());
    }
    const btnConfirmDeleteUser = document.getElementById('btn-confirm-delete-user-modal');
    if (btnConfirmDeleteUser) {
      btnConfirmDeleteUser.addEventListener('click', () => this.confirmDeleteUser());
    }
    const deleteUserModal = document.getElementById('delete-user-modal');
    if (deleteUserModal) {
      deleteUserModal.addEventListener('click', (e) => {
        if (e.target === deleteUserModal) this.closeDeleteUserModal();
      });
    }

    // Global keyboard listener for modal
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        const modal = document.getElementById('ticket-success-modal');
        if (modal && modal.style.display !== 'none') {
          this.closeSuccessModal();
        }
        const emailModal = document.getElementById('email-ticket-modal');
        if (emailModal && emailModal.style.display !== 'none') {
          this.closeEmailTicketModal();
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
        const createUsrModal = document.getElementById('create-user-modal');
        if (createUsrModal && createUsrModal.style.display !== 'none') {
          this.closeCreateUserModal();
        }
        const editUsrModal = document.getElementById('edit-user-modal');
        if (editUsrModal && editUsrModal.style.display !== 'none') {
          this.closeEditUserModal();
        }
        const resetUsrModal = document.getElementById('reset-user-password-modal');
        if (resetUsrModal && resetUsrModal.style.display !== 'none') {
          this.closeResetUserPasswordModal();
        }
        const delUsrModal = document.getElementById('delete-user-modal');
        if (delUsrModal && delUsrModal.style.display !== 'none') {
          this.closeDeleteUserModal();
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
    const user = Auth.getUser();
    const rol = (user && user.rol) ? user.rol.toUpperCase() : 'PM';

    // Restricciones de navegación por rol
    if (rol === 'PM') {
      moduleName = 'solicitud-lti';
    } else if (rol === 'LTI' && moduleName === 'usuarios') {
      moduleName = 'projects';
    }

    this.currentModule = moduleName;

    const navProjectsBtn = document.getElementById('nav-btn-projects');
    const navDirectSearchBtn = document.getElementById('nav-btn-direct-search');
    const navTicketsBtn = document.getElementById('nav-btn-tickets');
    const navSolicitudBtn = document.getElementById('nav-btn-solicitud-lti');
    const navUsuariosBtn = document.getElementById('nav-btn-usuarios');

    const moduleProjects = document.getElementById('module-projects-container');
    const moduleDirectSearch = document.getElementById('module-direct-search-container');
    const moduleTickets = document.getElementById('module-tickets-container');
    const moduleSolicitud = document.getElementById('module-solicitud-lti-container');
    const moduleUsuarios = document.getElementById('module-usuarios-container');

    if (navProjectsBtn) navProjectsBtn.classList.toggle('active', moduleName === 'projects');
    if (navDirectSearchBtn) navDirectSearchBtn.classList.toggle('active', moduleName === 'direct-search');
    if (navTicketsBtn) navTicketsBtn.classList.toggle('active', moduleName === 'tickets');
    if (navSolicitudBtn) navSolicitudBtn.classList.toggle('active', moduleName === 'solicitud-lti');
    if (navUsuariosBtn) navUsuariosBtn.classList.toggle('active', moduleName === 'usuarios');

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
    if (moduleUsuarios) {
      moduleUsuarios.style.display = moduleName === 'usuarios' ? 'block' : 'none';
      moduleUsuarios.classList.toggle('active', moduleName === 'usuarios');
    }

    if (moduleName === 'projects') {
      const selectSp = document.getElementById('filter-estado-sp');
      if (!this.estadosSharepoint || this.estadosSharepoint.length === 0 || (selectSp && selectSp.options.length <= 1)) {
        this.loadEstados();
      }
    } else if (moduleName === 'solicitud-lti') {
      this.loadSolicitudCatalogos();
      const fechaInput = document.getElementById('solicitud-fecha');
      if (fechaInput && !fechaInput.value) {
        const today = new Date();
        const year = today.getFullYear();
        const month = String(today.getMonth() + 1).padStart(2, '0');
        const day = String(today.getDate()).padStart(2, '0');
        fechaInput.value = `${year}-${month}-${day}`;
      }
    } else if (moduleName === 'usuarios') {
      this.loadUsuarios();
    }
  },

  // --------------------------------------------------------------------------
  // VIEW NAVIGATION & RBAC RULES
  // --------------------------------------------------------------------------
  applyRBACRules(rol) {
    const navProjects = document.getElementById('nav-btn-projects');
    const navDirectSearch = document.getElementById('nav-btn-direct-search');
    const navTickets = document.getElementById('nav-btn-tickets');
    const navSolicitud = document.getElementById('nav-btn-solicitud-lti');
    const navUsuarios = document.getElementById('nav-btn-usuarios');

    const rolUpper = (rol || '').toUpperCase();

    if (rolUpper === 'PM') {
      if (navProjects) navProjects.style.display = 'none';
      if (navDirectSearch) navDirectSearch.style.display = 'none';
      if (navTickets) navTickets.style.display = 'none';
      if (navSolicitud) navSolicitud.style.display = 'inline-flex';
      if (navUsuarios) navUsuarios.style.display = 'none';
    } else if (rolUpper === 'LTI') {
      if (navProjects) navProjects.style.display = 'inline-flex';
      if (navDirectSearch) navDirectSearch.style.display = 'inline-flex';
      if (navTickets) navTickets.style.display = 'inline-flex';
      if (navSolicitud) navSolicitud.style.display = 'inline-flex';
      if (navUsuarios) navUsuarios.style.display = 'none';
    } else if (rolUpper === 'ADMIN') {
      if (navProjects) navProjects.style.display = 'inline-flex';
      if (navDirectSearch) navDirectSearch.style.display = 'inline-flex';
      if (navTickets) navTickets.style.display = 'inline-flex';
      if (navSolicitud) navSolicitud.style.display = 'inline-flex';
      if (navUsuarios) navUsuarios.style.display = 'inline-flex';
    }
  },

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
        const rol = (user.rol || 'PM').toUpperCase();
        if (rol === 'ADMIN') {
          userRole.textContent = 'Administrador';
          userRole.className = 'badge badge-role-admin';
        } else if (rol === 'LTI') {
          userRole.textContent = 'Líder TI';
          userRole.className = 'badge badge-role-lti';
        } else {
          userRole.textContent = 'Project Manager';
          userRole.className = 'badge badge-role-pm';
        }
      }
      this.applyRBACRules(user.rol);
    }

    let initialModule = 'projects';
    if (user && user.rol === 'PM') {
      initialModule = 'solicitud-lti';
    }
    this.switchModule(initialModule);
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
    
    const btnDdDelete = document.getElementById('btn-dd-delete-project');
    if (btnDdDelete) {
      const user = Auth.getUser();
      btnDdDelete.style.display = (user && (user.rol || '').toUpperCase() === 'ADMIN') ? 'inline-flex' : 'none';
    }

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
    const selectSp = document.getElementById('filter-estado-sp');
    const previousValue = selectSp ? selectSp.value : '';

    try {
      const res = await Auth.fetchWithAuth('/api/estados');
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      
      // Asignación con fallback canónico si la lista viene vacía
      if (Array.isArray(data.estados_sharepoint) && data.estados_sharepoint.length > 0) {
        this.estadosSharepoint = data.estados_sharepoint;
      } else {
        this.estadosSharepoint = [...CANONICAL_ESTADOS_SHAREPOINT];
      }
    } catch (e) {
      console.warn('No se pudieron obtener los estados desde API, aplicando catálogo canónico:', e);
      this.estadosSharepoint = [...CANONICAL_ESTADOS_SHAREPOINT];
    }

    if (selectSp) {
      selectSp.innerHTML = '';
      
      // 1. Opción por defecto (Todos)
      const defaultOpt = document.createElement('option');
      defaultOpt.value = '';
      defaultOpt.textContent = '— Estado Sharepoint (Todos) —';
      selectSp.appendChild(defaultOpt);

      // 2. Opciones canónicas
      this.estadosSharepoint.forEach(est => {
        const opt = document.createElement('option');
        opt.value = est;
        opt.textContent = est;
        selectSp.appendChild(opt);
      });

      // 3. Restaurar valor previamente seleccionado si sigue existiendo
      if (previousValue && this.estadosSharepoint.includes(previousValue)) {
        selectSp.value = previousValue;
      }
    }
  },

  _kpisRequestId: 0,
  async loadKPIs() {
    const currentReqId = ++this._kpisRequestId;
    try {
      const ltFilter = document.getElementById('filter-lt')?.value || '';
      let url = '/api/kpis';
      if (ltFilter) {
        url += `?lt=${encodeURIComponent(ltFilter)}`;
      }
      
      const res = await Auth.fetchWithAuth(url);
      const kpis = await res.json();

      if (this._kpisRequestId !== currentReqId) return;

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

  _projectsRequestId: 0,
  async loadProjects() {
    const tbody = document.getElementById('projects-table-body');
    if (!tbody) return;

    this._projectsRequestId = (Number(this._projectsRequestId) || 0) + 1;
    const currentReqId = this._projectsRequestId;
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
      const data = await res.json();

      if (this._projectsRequestId !== currentReqId) return;

      this.projectsData = data;
      this.renderProjectsTable(this.projectsData);

      // Update count badge
      const countBadge = document.getElementById('projects-count-badge');
      if (countBadge) {
        countBadge.textContent = this.projectsData.length;
      }
    } catch (e) {
      if (this._projectsRequestId !== currentReqId) return;
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

    const user = Auth.getUser();
    const isAdmin = user && (user.rol || '').toUpperCase() === 'ADMIN';

    tbody.innerHTML = proyectos.map(p => {
      const solicitanteFormatted = this.formatSolicitante(p.Solicitante);
      const isUnmatched = solicitanteFormatted.startsWith('NO IDENTIFICADO');
      const deleteBtnHtml = isAdmin
        ? `<button type="button" class="btn-action-icon btn-action-delete" onclick="App.openDeleteProjectModal(${p.ID})" title="Eliminar proyecto" aria-label="Eliminar Proyecto">🗑️</button>`
        : '';

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
              ${deleteBtnHtml}
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
    if (!payload.contacto || !payload.titulo || !payload.descripcion || !payload.area || !payload.subarea || !payload.detalle || !payload.grupo || !payload.impacto || !payload.urgencia) {
      alert('Por favor completa todos los campos obligatorios (*) antes de iniciar la automatización.');
      return;
    }
    if (payload.titulo.length < 4) {
      alert('El título de la interacción debe contener al menos 4 caracteres.');
      return;
    }
    if (payload.descripcion.length < 5) {
      alert('La descripción debe contener al menos 5 caracteres.');
      return;
    }

    this.lastTicketFormData = { ...payload };

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
      const progress = eventData.progress;
      this.appendLogEntry(message, level);

      // If backend provides an explicit progress percentage, apply it
      if (typeof progress === 'number') {
        this.updateTicketProgress(progress);
      }

      // Estimate progress and update step text according to message content
      const msgLower = message.toLowerCase();
      if (msgLower.includes('iniciando proceso') || msgLower.includes('iniciando navegador')) {
        if (progress === undefined) this.updateTicketProgress(12);
        this.updateTicketStatus('running', 'En ejecución', 'Iniciando navegador Chromium...');
      } else if (msgLower.includes('conectando a portal')) {
        if (progress === undefined) this.updateTicketProgress(22);
        this.updateTicketStatus('running', 'En ejecución', 'Conectando al portal Service Manager...');
      } else if (msgLower.includes('autenticando')) {
        if (progress === undefined) this.updateTicketProgress(30);
        this.updateTicketStatus('running', 'En ejecución', 'Autenticando en portal...');
      } else if (msgLower.includes('centro de servicios') || msgLower.includes('servicios internos')) {
        if (progress === undefined) this.updateTicketProgress(40);
        this.updateTicketStatus('running', 'En ejecución', 'Navegando a formulario de interacción...');
      } else if (msgLower.includes('ingresando contacto') || msgLower.includes('título') || msgLower.includes('descripción') || msgLower.includes('formulario de interacción')) {
        if (progress === undefined) this.updateTicketProgress(50);
        this.updateTicketStatus('running', 'En ejecución', 'Llenando datos del formulario...');
      } else if (msgLower.includes('grupo') || msgLower.includes('asignando grupo')) {
        if (progress === undefined) this.updateTicketProgress(60);
        this.updateTicketStatus('running', 'En ejecución', 'Asignando grupo de asignación...');
      } else if (msgLower.includes('guardando interacción') || (msgLower.includes('guardar') && !msgLower.includes('petición') && !msgLower.includes('salir'))) {
        if (progress === undefined) this.updateTicketProgress(70);
        this.updateTicketStatus('running', 'En ejecución', 'Guardando interacción en Service Manager...');
      } else if (msgLower.includes('interacción generada') || (msgLower.includes('ticket generado') && !msgLower.includes('petición'))) {
        if (progress === undefined) this.updateTicketProgress(75);
        this.updateTicketStatus('running', 'En ejecución', 'Interacción SD generada exitosamente...');
      } else if (msgLower.includes('registros relacionados') || msgLower.includes('vinculando petición') || msgLower.includes('peticiones relacionadas')) {
        if (progress === undefined) this.updateTicketProgress(80);
        this.updateTicketStatus('running', 'En ejecución', 'Vinculando petición relacionada...');
      } else if (msgLower.includes('alejandro.aguilar') || msgLower.includes('responsable') || msgLower.includes('guardando formulario de la petición') || msgLower.includes('guardando petición')) {
        if (progress === undefined) this.updateTicketProgress(85);
        this.updateTicketStatus('running', 'En ejecución', 'Configurando usuario y guardando petición...');
      } else if (msgLower.includes('petición generada exitosamente') || msgLower.includes('petición generada')) {
        if (progress === undefined) this.updateTicketProgress(90);
        this.updateTicketStatus('running', 'En ejecución', '¡Petición generada exitosamente!');
      } else if (msgLower.includes('cerrando formularios') || msgLower.includes('cerrando sesión') || msgLower.includes('logout') || msgLower.includes('guardar y salir')) {
        if (progress === undefined) this.updateTicketProgress(95);
        this.updateTicketStatus('running', 'En ejecución', 'Cerrando sesión en Service Manager (Logout)...');
      } else if (level === 'error') {
        this.updateTicketStatus('error', 'Error', 'Error en la ejecución');
      }
    } else if (eventData.type === 'complete') {
      this.updateTicketProgress(100);
      this.updateTicketStatus('active', 'Completado', '¡Interacción y Petición creadas con éxito!');
      const ticketId = eventData.ticket_id || 'SD0000000';
      const peticionId = eventData.peticion_id || '-';
      const dataPayload = eventData.data || formData;
      this.openTicketSuccessModal(ticketId, peticionId, dataPayload);
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

    // Format message text: highlight ticket IDs (SD..., IM..., PET..., REQ...)
    let formattedMsg = this.escapeHtml(message);
    formattedMsg = formattedMsg.replace(/\b(SD-?\d{4,12}|IM-?\d{4,12}|PET-?\d{3,12}|REQ-?\d{3,12})\b/gi, '<span class="log-ticket-badge">$1</span>');

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

  openTicketSuccessModal(ticketId, peticionId = '-', formData = {}) {
    const modal = document.getElementById('ticket-success-modal');
    if (!modal) return;

    this.lastGeneratedTicketId = ticketId || 'SD0000000';
    this.lastGeneratedPeticionId = peticionId || '-';
    this.lastTicketFormData = formData && Object.keys(formData).length > 0 ? { ...formData } : (this.lastTicketFormData || {});

    const ticketIdEl = document.getElementById('ticket-success-id');
    if (ticketIdEl) ticketIdEl.textContent = this.lastGeneratedTicketId;

    const peticionIdEl = document.getElementById('peticion-success-id');
    if (peticionIdEl) peticionIdEl.textContent = this.lastGeneratedPeticionId;

    const contactoEl = document.getElementById('modal-summary-contacto');
    if (contactoEl) contactoEl.textContent = formData.contacto || 'ALEJANDRO JAVIER AGUILAR MORALES';

    const tituloEl = document.getElementById('modal-summary-titulo');
    if (tituloEl) tituloEl.textContent = formData.titulo || '-';

    const grupoEl = document.getElementById('modal-summary-grupo');
    if (grupoEl) grupoEl.textContent = formData.grupo || 'Lideres Tecnicos';

    const areaEl = document.getElementById('modal-summary-area');
    if (areaEl) {
      const areaStr = [formData.area || 'Proyectos', formData.subarea || 'Apoyo habilitacion cliente'].join(' / ');
      areaEl.textContent = areaStr;
    }

    const usuarioPetEl = document.getElementById('modal-summary-usuario-peticion');
    if (usuarioPetEl) usuarioPetEl.textContent = 'Alejandro.Aguilar';

    const feedbackTicketEl = document.getElementById('ticket-copy-feedback');
    if (feedbackTicketEl) feedbackTicketEl.style.display = 'none';

    const feedbackPetEl = document.getElementById('peticion-copy-feedback');
    if (feedbackPetEl) feedbackPetEl.style.display = 'none';

    const copyTicketBtnText = document.getElementById('copy-ticket-btn-text');
    if (copyTicketBtnText) copyTicketBtnText.textContent = '📋 Copiar SD';

    const copyPeticionBtnText = document.getElementById('copy-peticion-btn-text');
    if (copyPeticionBtnText) copyPeticionBtnText.textContent = '📋 Copiar Petición';

    modal.style.display = 'flex';

    // Foco automático en el botón de confirmación para accesibilidad por teclado
    setTimeout(() => {
      const closeBtn = document.getElementById('btn-close-success-modal');
      if (closeBtn) closeBtn.focus();
    }, 50);
  },

  closeSuccessModal() {
    const modal = document.getElementById('ticket-success-modal');
    if (modal) {
      modal.style.display = 'none';
    }
    const execBtn = document.getElementById('btn-execute-ticket');
    if (execBtn) {
      execBtn.focus();
    }
  },

  async copyTicketIdToClipboard() {
    const idEl = document.getElementById('ticket-success-id');
    const feedbackEl = document.getElementById('ticket-copy-feedback');
    const btnTextEl = document.getElementById('copy-ticket-btn-text');
    const btn = document.getElementById('btn-copy-ticket-id');

    const ticketId = idEl ? idEl.textContent.trim() : (this.lastGeneratedTicketId || '');
    if (!ticketId) return;

    const ok = await this.copyTextToClipboard(ticketId);
    if (ok) {
      if (feedbackEl) feedbackEl.style.display = 'block';
      if (btnTextEl) btnTextEl.textContent = '✓ ¡Copiado!';
      if (btn) btn.classList.add('btn-success');

      setTimeout(() => {
        if (feedbackEl) feedbackEl.style.display = 'none';
        if (btnTextEl) btnTextEl.textContent = '📋 Copiar SD';
        if (btn) btn.classList.remove('btn-success');
      }, 2500);
    }
  },

  async copyPeticionIdToClipboard() {
    const idEl = document.getElementById('peticion-success-id');
    const feedbackEl = document.getElementById('peticion-copy-feedback');
    const btnTextEl = document.getElementById('copy-peticion-btn-text');
    const btn = document.getElementById('btn-copy-peticion-id');

    const peticionId = idEl ? idEl.textContent.trim() : (this.lastGeneratedPeticionId || '');
    if (!peticionId || peticionId === '-') return;

    const ok = await this.copyTextToClipboard(peticionId);
    if (ok) {
      if (feedbackEl) feedbackEl.style.display = 'block';
      if (btnTextEl) btnTextEl.textContent = '✓ ¡Copiado!';
      if (btn) btn.classList.add('btn-success');

      setTimeout(() => {
        if (feedbackEl) feedbackEl.style.display = 'none';
        if (btnTextEl) btnTextEl.textContent = '📋 Copiar Petición';
        if (btn) btn.classList.remove('btn-success');
      }, 2500);
    }
  },

  async copyBothIdsToClipboard() {
    const ticketId = (document.getElementById('ticket-success-id')?.textContent || this.lastGeneratedTicketId || '').trim();
    const peticionId = (document.getElementById('peticion-success-id')?.textContent || this.lastGeneratedPeticionId || '').trim();
    const contacto = (document.getElementById('modal-summary-contacto')?.textContent || '').trim();
    const titulo = (document.getElementById('modal-summary-titulo')?.textContent || '').trim();
    const grupo = (document.getElementById('modal-summary-grupo')?.textContent || '').trim();
    const area = (document.getElementById('modal-summary-area')?.textContent || '').trim();
    const usuarioPeticion = (document.getElementById('modal-summary-usuario-peticion')?.textContent || 'Alejandro.Aguilar').trim();
    const btn = document.getElementById('btn-copy-both-ids');

    const textToCopy = `[Service Manager] Automatización Exitosa
- ID Interacción (SD): ${ticketId}
- ID Petición: ${peticionId}
- Contacto: ${contacto}
- Título: ${titulo}
- Grupo: ${grupo}
- Área/Subárea: ${area}
- Usuario Petición: ${usuarioPeticion}`;

    const ok = await this.copyTextToClipboard(textToCopy);
    if (ok && btn) {
      const origText = btn.innerHTML;
      btn.innerHTML = '✓ ¡Resumen Copiado!';
      btn.classList.add('btn-success');
      setTimeout(() => {
        btn.innerHTML = origText;
        btn.classList.remove('btn-success');
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
  // MODAL: ENVIAR DETALLE DEL TICKET POR CORREO (OFFICE 365)
  // --------------------------------------------------------------------------
  openEmailTicketModal() {
    const modal = document.getElementById('email-ticket-modal');
    if (!modal) return;

    // Guardar el elemento activo para retornar foco al cerrar
    this.lastActiveElementBeforeEmailModal = document.activeElement;

    // Reset error / status alert banner
    const alertEl = document.getElementById('email-status-alert') || document.getElementById('email-error-alert');
    if (alertEl) {
      alertEl.style.display = 'none';
      alertEl.className = 'solicitud-alert-banner alert-danger';
    }

    // Pre-fill recipient (Para)
    const toInput = document.getElementById('email-destinatario') || document.getElementById('email-to');
    if (toInput) {
      toInput.value = 'alejandro.aguilarm@clarovtr.cl';
    }

    // Pre-fill Subject (Asunto)
    const subjectInput = document.getElementById('email-asunto') || document.getElementById('email-subject');
    if (subjectInput) {
      const defaultTitle = this.lastTicketFormData?.titulo || document.getElementById('ticket-titulo')?.value?.trim() || '';
      subjectInput.value = defaultTitle ? `Interacción Service Manager: ${defaultTitle}` : (this.lastGeneratedTicketId ? `Interacción ${this.lastGeneratedTicketId}` : 'Interacción Service Manager');
    }

    // Pre-fill Body (Cuerpo)
    const bodyInput = document.getElementById('email-cuerpo') || document.getElementById('email-body');
    if (bodyInput) {
      const defaultDesc = this.lastTicketFormData?.descripcion || document.getElementById('ticket-descripcion')?.value?.trim() || '';
      bodyInput.value = defaultDesc || (this.lastGeneratedTicketId ? `Interacción ${this.lastGeneratedTicketId} generada exitosamente.` : '');
    }

    // Update ticket badges
    const badgeTicket = document.getElementById('email-badge-ticket-id');
    if (badgeTicket) {
      badgeTicket.textContent = this.lastGeneratedTicketId || 'SD0000000';
    }
    const badgePeticion = document.getElementById('email-badge-peticion-id');
    if (badgePeticion) {
      badgePeticion.textContent = this.lastGeneratedPeticionId || 'PET0000000';
    }

    // Reset attachment state
    this.clearEmailAttachment();

    // Reset button states
    this.setEmailSendingState(false);

    // Show modal
    modal.style.display = 'flex';

    // Focus on recipient input
    setTimeout(() => {
      if (toInput) toInput.focus();
    }, 50);
  },

  closeEmailTicketModal() {
    const modal = document.getElementById('email-ticket-modal');
    if (modal) {
      modal.style.display = 'none';
    }
    this.setEmailSendingState(false);

    // Restaurar foco al elemento que abrió el modal
    if (this.lastActiveElementBeforeEmailModal && typeof this.lastActiveElementBeforeEmailModal.focus === 'function') {
      try {
        this.lastActiveElementBeforeEmailModal.focus();
      } catch (err) {
        // Ignorar si el elemento ya no está en el DOM
      }
    }
  },

  handleEmailFileSelect(file) {
    if (!file) return;

    const MAX_SIZE = 15 * 1024 * 1024; // 15MB
    if (file.size > MAX_SIZE) {
      this.showEmailAlert(
        'Archivo supera el límite',
        'El archivo adjunto supera el tamaño máximo permitido de 15 MB. Por favor selecciona un archivo más pequeño.'
      );
      this.clearEmailAttachment();
      return;
    }

    this.selectedEmailFile = file;

    const emptyState = document.getElementById('attachment-empty-state');
    const selectedState = document.getElementById('attachment-selected-state');
    const filenameEl = document.getElementById('attachment-filename');
    const filesizeEl = document.getElementById('attachment-filesize');

    if (emptyState) emptyState.style.display = 'none';
    if (selectedState) selectedState.style.display = 'flex';
    if (filenameEl) filenameEl.textContent = file.name;
    if (filesizeEl) {
      const sizeKb = (file.size / 1024).toFixed(1);
      const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
      filesizeEl.textContent = file.size > 1024 * 1024 ? `${sizeMb} MB` : `${sizeKb} KB`;
    }
  },

  clearEmailAttachment() {
    this.selectedEmailFile = null;
    const fileInput = document.getElementById('email-adjunto') || document.getElementById('email-attachment');
    if (fileInput) fileInput.value = '';

    const emptyState = document.getElementById('attachment-empty-state');
    const selectedState = document.getElementById('attachment-selected-state');
    if (emptyState) emptyState.style.display = 'block';
    if (selectedState) selectedState.style.display = 'none';
  },

  showEmailAlert(title, message, isSuccess = false) {
    const alertEl = document.getElementById('email-status-alert') || document.getElementById('email-error-alert');
    if (!alertEl) return;

    alertEl.className = isSuccess ? 'solicitud-alert-banner alert-success' : 'solicitud-alert-banner alert-danger';

    const iconEl = document.getElementById('email-status-alert-icon') || alertEl.querySelector('.alert-icon');
    if (iconEl) iconEl.textContent = isSuccess ? '✓' : '❌';

    const titleEl = document.getElementById('email-error-title');
    if (titleEl) titleEl.textContent = title;

    const descEl = document.getElementById('email-error-desc');
    if (descEl) descEl.textContent = message;

    alertEl.style.display = 'flex';
  },

  setEmailSendingState(isSending) {
    this.isEmailSending = isSending;
    const sendBtn = document.getElementById('btn-send-email') || document.getElementById('btn-send-email-submit');
    const cancelBtn = document.getElementById('btn-cancel-email') || document.getElementById('btn-cancel-email-modal');
    const spinner = document.getElementById('email-spinner') || document.getElementById('email-send-spinner');
    const sendIcon = document.getElementById('email-send-icon');
    const sendText = document.getElementById('email-send-text');

    if (sendBtn) sendBtn.disabled = isSending;
    if (cancelBtn) cancelBtn.disabled = isSending;

    if (spinner) spinner.style.display = isSending ? 'inline-block' : 'none';
    if (sendIcon) sendIcon.style.display = isSending ? 'none' : 'inline';
    if (sendText) sendText.textContent = isSending ? 'Enviando...' : 'Enviar';
  },

  async submitSendTicketEmail() {
    if (this.isEmailSending) return;

    const toInput = document.getElementById('email-destinatario') || document.getElementById('email-to');
    const subjectInput = document.getElementById('email-asunto') || document.getElementById('email-subject');
    const bodyInput = document.getElementById('email-cuerpo') || document.getElementById('email-body');

    const toEmail = toInput ? toInput.value.trim() : '';
    const subject = subjectInput ? subjectInput.value.trim() : '';
    const body = bodyInput ? bodyInput.value.trim() : '';

    if (!toEmail) {
      this.showEmailAlert('Destinatario requerido', 'Por favor ingresa al menos una dirección de correo válida.');
      if (toInput) toInput.focus();
      return;
    }

    if (!subject) {
      this.showEmailAlert('Asunto requerido', 'Por favor ingresa el asunto del correo.');
      if (subjectInput) subjectInput.focus();
      return;
    }

    if (!body) {
      this.showEmailAlert('Cuerpo requerido', 'Por favor ingresa el contenido o cuerpo del mensaje.');
      if (bodyInput) bodyInput.focus();
      return;
    }

    // Hide previous alerts
    const alertEl = document.getElementById('email-status-alert') || document.getElementById('email-error-alert');
    if (alertEl) alertEl.style.display = 'none';

    // Prepare FormData
    const formData = new FormData();
    formData.append('to_email', toEmail);
    formData.append('para', toEmail);
    formData.append('subject', subject);
    formData.append('asunto', subject);
    formData.append('body', body);
    formData.append('cuerpo', body);

    if (this.lastGeneratedTicketId) {
      formData.append('ticket_id', this.lastGeneratedTicketId);
    }
    if (this.lastGeneratedPeticionId) {
      formData.append('peticion_id', this.lastGeneratedPeticionId);
    }

    if (this.selectedEmailFile) {
      formData.append('attachment', this.selectedEmailFile);
      formData.append('adjunto', this.selectedEmailFile);
    }

    this.setEmailSendingState(true);

    try {
      const response = await Auth.fetchWithAuth('/api/automation/send-ticket-email', {
        method: 'POST',
        body: formData
      });

      const resData = await response.json().catch(() => null);

      if (!response.ok) {
        const errorDetail = resData?.detail || `Error al enviar correo (HTTP ${response.status})`;
        throw new Error(errorDetail);
      }

      // Success toast & close modal
      this.showToast(`✓ Correo enviado exitosamente a ${toEmail}`, 'success');
      this.closeEmailTicketModal();

    } catch (err) {
      console.error('Error enviando correo de ticket:', err);
      this.showEmailAlert(
        'No se pudo enviar el correo',
        err.message || 'Ocurrió un error inesperado al contactar al servidor SMTP.'
      );
    } finally {
      this.setEmailSendingState(false);
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
        const currentProj = document.getElementById('solicitud-nro-proyecto')?.value?.trim();
        if (!currentProj || !currentProj.includes(String(nroProyecto).trim())) {
          return; // Form was reset or project number changed while in-flight
        }
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
  // MÓDULO: MANTENEDOR DE USUARIOS & ROLES (CRUD)
  // --------------------------------------------------------------------------
  async loadUsuarios() {
    const search = document.getElementById('usuarios-search-input')?.value || '';
    const rol = document.getElementById('usuarios-filter-rol')?.value || '';
    const estado = document.getElementById('usuarios-filter-estado')?.value || '';

    const params = new URLSearchParams();
    if (search.trim()) params.append('search', search.trim());
    if (rol.trim()) params.append('rol', rol.trim());
    if (estado.trim() !== '') params.append('activo', estado.trim());

    const tbody = document.getElementById('usuarios-table-body');
    if (tbody) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 2rem; color: var(--text-secondary);">Cargando usuarios...</td></tr>';
    }

    try {
      const res = await Auth.fetchWithAuth(`/api/usuarios?${params.toString()}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Error al consultar usuarios' }));
        throw new Error(err.detail || 'Error al consultar usuarios');
      }
      this.usuariosData = await res.json();
      this.renderUsuariosTable(this.usuariosData);

      const countBadge = document.getElementById('usuarios-count-badge');
      if (countBadge) {
        countBadge.textContent = this.usuariosData.length;
      }
    } catch (e) {
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 2rem; color: var(--status-danger-text);">Error al cargar usuarios: ${e.message}</td></tr>`;
      }
      const countBadge = document.getElementById('usuarios-count-badge');
      if (countBadge) countBadge.textContent = '0';
    }
  },

  renderUsuariosTable(usuarios) {
    const tbody = document.getElementById('usuarios-table-body');
    if (!tbody) return;

    if (!usuarios || usuarios.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="8">
            <div class="empty-state">
              <div class="empty-icon">👥</div>
              <h3>No se encontraron usuarios</h3>
              <p>Intenta ajustar los filtros de búsqueda o seleccionar otro Rol / Estado.</p>
            </div>
          </td>
        </tr>
      `;
      return;
    }

    const currentUser = Auth.getUser();

    tbody.innerHTML = usuarios.map(u => {
      let roleBadge = '';
      const r = (u.rol || 'PM').toUpperCase();
      if (r === 'ADMIN') {
        roleBadge = '<span class="badge-role-admin">🛡️ ADMIN</span>';
      } else if (r === 'LTI') {
        roleBadge = '<span class="badge-role-lti">👔 LTI</span>';
      } else {
        roleBadge = '<span class="badge-role-pm">📋 PM</span>';
      }

      const statusBadge = u.activo
        ? '<span class="badge-status-active">✓ Activo</span>'
        : '<span class="badge-status-blocked">✕ Bloqueado</span>';

      const toggleIcon = u.activo ? '🔒' : '🔓';
      const toggleTitle = u.activo ? 'Bloquear usuario' : 'Desbloquear usuario';

      const isSelf = currentUser && String(currentUser.id) === String(u.id);
      const isRootAdmin = u.username === 'admin';

      return `
        <tr>
          <td><span style="font-family: var(--font-mono); font-weight: 700; color: var(--text-secondary);">${u.id}</span></td>
          <td><strong style="font-family: var(--font-mono); color: var(--primary);">${this.escapeHtml(u.username)}</strong></td>
          <td><strong>${this.escapeHtml(u.nombre_completo)}</strong></td>
          <td>${roleBadge}</td>
          <td>${this.escapeHtml(u.lt_asignado || '—')}</td>
          <td>${statusBadge}</td>
          <td><small style="color: var(--text-secondary); font-weight: 600;">${this.formatDateDMY(u.created_at)}</small></td>
          <td class="col-action-cell">
            <div class="action-buttons-group">
              <button type="button" class="btn-action-user-edit" onclick="App.openEditUserModal(${u.id})" title="Editar usuario" aria-label="Editar Usuario">
                ✏️
              </button>
              <button type="button" class="btn-action-user-key" onclick="App.openResetUserPasswordModal(${u.id})" title="Resetear contraseña" aria-label="Resetear Contraseña">
                🔑
              </button>
              <button type="button" class="btn-action-user-toggle" onclick="App.toggleUserStatus(${u.id})" title="${toggleTitle}" aria-label="${toggleTitle}" ${(isSelf || isRootAdmin) ? 'disabled style="opacity: 0.4; cursor: not-allowed;"' : ''}>
                ${toggleIcon}
              </button>
              <button type="button" class="btn-action-user-delete" onclick="App.openDeleteUserModal(${u.id})" title="Eliminar usuario" aria-label="Eliminar Usuario" ${(isSelf || isRootAdmin) ? 'disabled style="opacity: 0.4; cursor: not-allowed;"' : ''}>
                🗑️
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join('');
  },

  openCreateUserModal() {
    const modal = document.getElementById('create-user-modal');
    if (!modal) return;

    const errAlert = document.getElementById('create-user-error-alert');
    if (errAlert) errAlert.style.display = 'none';

    document.getElementById('create-user-nombre').value = '';
    document.getElementById('create-user-username').value = '';
    document.getElementById('create-user-password').value = 'Lti2026!';
    document.getElementById('create-user-rol').value = 'PM';
    document.getElementById('create-user-activo').value = '1';

    const selectLt = document.getElementById('create-user-lt-asignado');
    if (selectLt) {
      selectLt.innerHTML = '<option value="">— Ninguno / No Aplica —</option>';
      this.lideresList.forEach(lt => {
        const opt = document.createElement('option');
        opt.value = lt;
        opt.textContent = lt;
        selectLt.appendChild(opt);
      });
    }

    modal.style.display = 'flex';
  },

  closeCreateUserModal() {
    const modal = document.getElementById('create-user-modal');
    if (modal) modal.style.display = 'none';
  },

  async submitCreateUserForm() {
    if (this.isUserSubmitting) return;

    const nombre = document.getElementById('create-user-nombre')?.value.trim();
    const username = document.getElementById('create-user-username')?.value.trim();
    const password = document.getElementById('create-user-password')?.value;
    const rol = document.getElementById('create-user-rol')?.value;
    const ltAsignado = document.getElementById('create-user-lt-asignado')?.value.trim() || null;
    const activo = document.getElementById('create-user-activo')?.value === '1';

    const errAlert = document.getElementById('create-user-error-alert');
    const errDesc = document.getElementById('create-user-error-desc');
    const spinner = document.getElementById('create-user-spinner');
    const btn = document.getElementById('btn-save-create-user-modal');

    if (!nombre || !username || !password || !rol) {
      if (errAlert && errDesc) {
        errDesc.textContent = 'Todos los campos obligatorios (*) deben ser completados.';
        errAlert.style.display = 'flex';
      }
      return;
    }

    if (password.length < 6) {
      if (errAlert && errDesc) {
        errDesc.textContent = 'La contraseña debe tener al menos 6 caracteres.';
        errAlert.style.display = 'flex';
      }
      return;
    }

    this.isUserSubmitting = true;
    if (btn) btn.disabled = true;
    if (spinner) spinner.style.display = 'inline-block';
    if (errAlert) errAlert.style.display = 'none';

    try {
      const res = await Auth.fetchWithAuth('/api/usuarios', {
        method: 'POST',
        body: JSON.stringify({
          nombre_completo: nombre,
          username: username,
          password: password,
          rol: rol,
          lt_asignado: ltAsignado,
          activo: activo
        })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Error al crear usuario' }));
        throw new Error(err.detail || 'Error al crear usuario');
      }

      const newUser = await res.json();
      this.closeCreateUserModal();
      this.showToast(`Usuario '${newUser.username}' creado exitosamente`, 'success');
      await this.loadUsuarios();
    } catch (err) {
      if (errAlert && errDesc) {
        errDesc.textContent = err.message || 'Error al procesar la solicitud.';
        errAlert.style.display = 'flex';
      }
    } finally {
      this.isUserSubmitting = false;
      if (btn) btn.disabled = false;
      if (spinner) spinner.style.display = 'none';
    }
  },

  async openEditUserModal(userId) {
    const modal = document.getElementById('edit-user-modal');
    if (!modal) return;

    this.currentEditingUserId = userId;
    const idInput = document.getElementById('edit-user-id');
    if (idInput) idInput.value = userId;

    const errAlert = document.getElementById('edit-user-error-alert');
    if (errAlert) errAlert.style.display = 'none';

    let user = this.usuariosData?.find(u => String(u.id) === String(userId));
    if (!user) {
      try {
        const res = await Auth.fetchWithAuth(`/api/usuarios/${userId}`);
        if (res.ok) {
          user = await res.json();
        }
      } catch (e) {
        console.warn('Error fetching user for edit modal:', e);
      }
    }

    if (user) {
      if (idInput) idInput.value = user.id;
      const usernameInput = document.getElementById('edit-user-username');
      if (usernameInput) usernameInput.value = user.username || '';
      
      const nombreInput = document.getElementById('edit-user-nombre');
      if (nombreInput) nombreInput.value = user.nombre_completo || '';
      
      const rolSelect = document.getElementById('edit-user-rol');
      if (rolSelect) rolSelect.value = user.rol || 'PM';
      
      const activoSelect = document.getElementById('edit-user-activo');
      if (activoSelect) activoSelect.value = user.activo ? '1' : '0';

      const selectLt = document.getElementById('edit-user-lt-asignado');
      if (selectLt) {
        selectLt.innerHTML = '<option value="">— Ninguno / No Aplica —</option>';
        this.lideresList.forEach(lt => {
          const opt = document.createElement('option');
          opt.value = lt;
          opt.textContent = lt;
          if (user.lt_asignado === lt) {
            opt.selected = true;
          }
          selectLt.appendChild(opt);
        });
      }
    }

    modal.style.display = 'flex';
  },

  closeEditUserModal() {
    const modal = document.getElementById('edit-user-modal');
    if (modal) modal.style.display = 'none';
    this.currentEditingUserId = null;
  },

  async submitEditUserForm() {
    if (this.isUserSubmitting) return;

    const userId = this.currentEditingUserId || document.getElementById('edit-user-id')?.value;
    const nombre = document.getElementById('edit-user-nombre')?.value.trim();
    const rol = document.getElementById('edit-user-rol')?.value;
    const ltAsignado = document.getElementById('edit-user-lt-asignado')?.value.trim() || null;
    const activo = document.getElementById('edit-user-activo')?.value === '1';

    const errAlert = document.getElementById('edit-user-error-alert');
    const errDesc = document.getElementById('edit-user-error-desc');
    const spinner = document.getElementById('edit-user-spinner');
    const btn = document.getElementById('btn-save-edit-user-modal');

    if (!userId || !nombre || !rol) {
      if (errAlert && errDesc) {
        errDesc.textContent = 'El nombre completo y rol son obligatorios.';
        errAlert.style.display = 'flex';
      }
      return;
    }

    this.isUserSubmitting = true;
    if (btn) btn.disabled = true;
    if (spinner) spinner.style.display = 'inline-block';
    if (errAlert) errAlert.style.display = 'none';

    try {
      const res = await Auth.fetchWithAuth(`/api/usuarios/${userId}`, {
        method: 'PUT',
        body: JSON.stringify({
          nombre_completo: nombre,
          rol: rol,
          lt_asignado: ltAsignado,
          activo: activo
        })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Error al actualizar usuario' }));
        throw new Error(err.detail || 'Error al actualizar usuario');
      }

      const updated = await res.json();
      this.closeEditUserModal();
      this.showToast(`Usuario '${updated.username}' actualizado exitosamente`, 'success');
      await this.loadUsuarios();
    } catch (err) {
      if (errAlert && errDesc) {
        errDesc.textContent = err.message || 'Error al procesar la actualización.';
        errAlert.style.display = 'flex';
      }
    } finally {
      this.isUserSubmitting = false;
      if (btn) btn.disabled = false;
      if (spinner) spinner.style.display = 'none';
    }
  },

  openResetUserPasswordModal(userId) {
    const modal = document.getElementById('reset-user-password-modal');
    if (!modal) return;

    const user = this.usuariosData.find(u => String(u.id) === String(userId));
    if (!user) return;

    document.getElementById('reset-user-id').value = user.id;
    document.getElementById('reset-user-username-display').textContent = user.username;
    document.getElementById('reset-user-nombre-display').textContent = user.nombre_completo;
    document.getElementById('reset-user-new-password').value = '';

    modal.style.display = 'flex';
  },

  closeResetUserPasswordModal() {
    const modal = document.getElementById('reset-user-password-modal');
    if (modal) modal.style.display = 'none';
  },

  async submitResetUserPasswordForm() {
    const userId = document.getElementById('reset-user-id')?.value;
    const newPass = document.getElementById('reset-user-new-password')?.value.trim();
    const spinner = document.getElementById('reset-user-spinner');
    const btn = document.getElementById('btn-confirm-reset-user-modal');

    if (!userId) return;

    if (btn) btn.disabled = true;
    if (spinner) spinner.style.display = 'inline-block';

    try {
      const res = await Auth.fetchWithAuth(`/api/usuarios/${userId}/reset-password`, {
        method: 'POST',
        body: JSON.stringify({
          new_password: newPass || 'Lti2026!'
        })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Error al resetear contraseña' }));
        throw new Error(err.detail || 'Error al resetear contraseña');
      }

      this.closeResetUserPasswordModal();
      this.showToast('Contraseña restablecida exitosamente', 'success');
    } catch (err) {
      this.showToast(`Error: ${err.message}`, 'danger');
    } finally {
      if (btn) btn.disabled = false;
      if (spinner) spinner.style.display = 'none';
    }
  },

  async toggleUserStatus(userId) {
    try {
      const res = await Auth.fetchWithAuth(`/api/usuarios/${userId}/toggle-status`, {
        method: 'PATCH'
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Error al cambiar estado' }));
        throw new Error(err.detail || 'Error al cambiar estado');
      }

      const data = await res.json();
      const statusText = data.activo ? 'activado' : 'bloqueado';
      this.showToast(`Usuario ${statusText} exitosamente`, 'success');
      await this.loadUsuarios();
    } catch (err) {
      this.showToast(`Error: ${err.message}`, 'danger');
    }
  },

  async openDeleteUserModal(userId) {
    const modal = document.getElementById('delete-user-modal');
    if (!modal) return;

    let user = this.usuariosData?.find(u => String(u.id) === String(userId));
    if (!user) {
      try {
        const res = await Auth.fetchWithAuth(`/api/usuarios/${userId}`);
        if (res.ok) {
          user = await res.json();
        }
      } catch (e) {
        console.warn('Error fetching user for delete modal:', e);
      }
    }

    this.userToDeleteId = user ? user.id : userId;
    const deleteIdInput = document.getElementById('delete-user-id');
    if (deleteIdInput) deleteIdInput.value = this.userToDeleteId;
    
    const userDisplay = document.getElementById('delete-user-username-display');
    if (userDisplay) userDisplay.textContent = user ? user.username : `ID: ${userId}`;
    
    const nombreDisplay = document.getElementById('delete-user-nombre-display');
    if (nombreDisplay) nombreDisplay.textContent = user ? user.nombre_completo : '';
    
    const rolDisplay = document.getElementById('delete-user-rol-display');
    if (rolDisplay) rolDisplay.textContent = user ? user.rol : '';

    modal.style.display = 'flex';
  },

  closeDeleteUserModal() {
    const modal = document.getElementById('delete-user-modal');
    if (modal) modal.style.display = 'none';
    this.userToDeleteId = null;
  },

  async confirmDeleteUser() {
    const userId = this.userToDeleteId || document.getElementById('delete-user-id')?.value;
    if (!userId) return;

    const spinner = document.getElementById('delete-user-spinner');
    const btn = document.getElementById('btn-confirm-delete-user-modal');

    if (btn) btn.disabled = true;
    if (spinner) spinner.style.display = 'inline-block';

    try {
      const res = await Auth.fetchWithAuth(`/api/usuarios/${userId}`, {
        method: 'DELETE'
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Error al eliminar usuario' }));
        throw new Error(err.detail || 'Error al eliminar usuario');
      }

      this.closeDeleteUserModal();
      this.showToast('Usuario eliminado permanentemente', 'success');
      await this.loadUsuarios();
    } catch (err) {
      this.showToast(`Error: ${err.message}`, 'danger');
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

window.App = App;

// Start application upon DOM load
document.addEventListener('DOMContentLoaded', () => App.init());
