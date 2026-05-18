class ReminderManagerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.reminders = [];
    this.availableUsers = [];
    this.availableNotifyTargets = [];
    this.availableZones = [];
    this.currentUser = null;
    this.intervalId = null;
    this.editingId = null;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.initialized) {
      this.initialized = true;
      this.render();
      this.fetchData();
      
      // Update timers visually every second
      this.intervalId = setInterval(() => {
        this.updateTimers();
      }, 1000);
      
      // Refresh data from backend every 10 seconds to sync state
      this.syncIntervalId = setInterval(() => {
        this.fetchData();
      }, 10000);
    }
  }

  async fetchData() {
    try {
      const selectedUsers = this.getSelectedValues("input-users");
      const selectedNotifyTargets = this.getSelectedValues("input-notify-targets");
      const selectedZone = this.shadowRoot.getElementById("input-zone-entity")?.value || "";
      const response = await this._hass.fetchWithAuth("/api/reminder_manager?include_meta=1");
      if (response.ok) {
        const payload = await response.json();
        if (Array.isArray(payload)) {
          this.reminders = payload;
        } else {
          this.reminders = payload.reminders || [];
          this.currentUser = payload.current_user || null;
          this.availableUsers = payload.available_users || [];
          this.availableNotifyTargets = payload.available_notify_targets || [];
          this.availableZones = payload.available_zones || [];
          this.renderRecipientOptions();
          this.setSelectedValues("input-users", selectedUsers);
          this.setSelectedValues("input-notify-targets", selectedNotifyTargets);
          const zoneSelect = this.shadowRoot.getElementById("input-zone-entity");
          if (zoneSelect && selectedZone) {
            zoneSelect.value = selectedZone;
          }
        }
        this.renderReminders();
      }
    } catch (err) {
      console.error("Error fetching reminders", err);
    }
  }

  async performAction(action, payload) {
    try {
      const response = await this._hass.fetchWithAuth("/api/reminder_manager", {
        method: "POST",
        body: JSON.stringify({ action, ...payload })
      });
      if (!response.ok) {
        const result = await response.json().catch(() => ({}));
        throw new Error(result.error || `Action ${action} failed`);
      }
      this.fetchData();
    } catch (err) {
      console.error("Error performing action", action, err);
      alert(err.message || "Actiunea a esuat.");
    }
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          box-sizing: border-box;
          padding: 16px;
          font-family: var(--paper-font-body1_-_font-family, sans-serif);
          background-color: var(--primary-background-color);
          color: var(--primary-text-color);
        }
        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 24px;
        }
        .header-main {
          display: flex;
          align-items: center;
          gap: 12px;
          min-width: 0;
        }
        .header-actions {
          display: flex;
          align-items: center;
          gap: 10px;
        }
        h1 {
          margin: 0;
          font-size: 24px;
        }
        button {
          background-color: var(--primary-color);
          color: var(--text-primary-color);
          border: none;
          padding: 8px 16px;
          border-radius: 4px;
          cursor: pointer;
          font-weight: bold;
        }
        button:hover {
          opacity: 0.9;
        }
        .button-secondary {
          background-color: var(--secondary-background-color);
          color: var(--primary-text-color);
        }
        .button-danger {
          background-color: var(--error-color);
        }
        .back-button {
          display: none;
          padding: 8px 12px;
          font-size: 14px;
          line-height: 1;
          white-space: nowrap;
        }
        .card {
          background-color: var(--card-background-color, white);
          border-radius: 14px;
          padding: 18px;
          margin-bottom: 16px;
          box-shadow: 0 10px 26px rgba(0,0,0,0.08);
          border: 1px solid rgba(127, 127, 127, 0.14);
        }
        .form-group {
          margin-bottom: 16px;
        }
        label {
          display: block;
          margin-bottom: 4px;
          font-weight: bold;
        }
        input[type="text"], input[type="number"], input[type="date"], input[type="time"], select {
          width: 100%;
          padding: 8px;
          border: 1px solid var(--divider-color, #ccc);
          border-radius: 4px;
          box-sizing: border-box;
          background-color: var(--card-background-color);
          color: var(--primary-text-color);
        }
        select[multiple] {
          min-height: 112px;
        }
        .field-help {
          margin-top: 6px;
          font-size: 12px;
          color: var(--secondary-text-color);
        }
        .progress-bar-container {
          width: 100%;
          background-color: var(--secondary-background-color);
          border-radius: 999px;
          height: 8px;
          overflow: hidden;
        }
        .progress-bar {
          height: 100%;
          background-color: var(--success-color, green);
          width: 0%;
          transition: width 1s linear;
        }
        .progress-bar.yellow { background-color: var(--warning-color, orange); }
        .progress-bar.red { background-color: var(--error-color, red); }
        
        #reminder-form {
          display: none;
        }
        .reminder-actions {
          display: flex;
          gap: 8px;
          align-items: center;
          flex-wrap: wrap;
        }
        .reminder-title {
          font-size: 28px;
          font-weight: bold;
          line-height: 1.1;
        }
        .reminder-message {
          font-size: 16px;
          color: var(--secondary-text-color);
        }
        .reminder-meta {
          font-size: 14px;
          color: var(--secondary-text-color);
        }
        .countdown {
          font-weight: bold;
          font-family: monospace;
          font-size: 20px;
        }
        .tabs {
          display: flex;
          gap: 16px;
          margin-bottom: 16px;
          border-bottom: 1px solid var(--divider-color);
        }
        .tab {
          padding: 8px 16px;
          cursor: pointer;
          border-bottom: 2px solid transparent;
        }
        .tab.active {
          border-bottom: 2px solid var(--primary-color);
          font-weight: bold;
        }
        .snooze-wrapper {
          display: flex;
          align-items: center;
          gap: 4px;
        }
        .snooze-wrapper select {
          width: auto;
          padding: 6px;
        }
        .reminders-grid {
          display: flex;
          flex-direction: column;
          gap: 18px;
        }
        .reminder-card {
          position: relative;
          background:
            linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0)),
            var(--card-background-color, white);
          border-radius: 18px;
          padding: 20px;
          border: 1px solid rgba(127, 127, 127, 0.15);
          box-shadow: 0 14px 36px rgba(0,0,0,0.08);
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .reminder-card.status-active {
          border-top: 4px solid var(--primary-color);
        }
        .reminder-card.status-expired {
          border-top: 4px solid var(--error-color);
        }
        .reminder-card.status-done {
          border-top: 4px solid var(--success-color, #2e7d32);
        }
        .reminder-card-header {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .reminder-status-badge {
          display: inline-flex;
          align-self: flex-start;
          align-items: center;
          padding: 6px 10px;
          border-radius: 999px;
          font-size: 12px;
          font-weight: 700;
          letter-spacing: 0.04em;
          text-transform: uppercase;
        }
        .status-badge-active {
          background: color-mix(in srgb, var(--primary-color) 14%, transparent);
          color: var(--primary-color);
        }
        .status-badge-expired {
          background: color-mix(in srgb, var(--error-color) 14%, transparent);
          color: var(--error-color);
        }
        .status-badge-done {
          background: color-mix(in srgb, var(--success-color, #2e7d32) 14%, transparent);
          color: var(--success-color, #2e7d32);
        }
        .reminder-meta-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 10px;
        }
        .reminder-meta-card {
          background: color-mix(in srgb, var(--primary-background-color) 58%, transparent);
          border: 1px solid rgba(127, 127, 127, 0.12);
          border-radius: 12px;
          padding: 10px 12px;
          min-width: 0;
        }
        .reminder-meta-label {
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.05em;
          text-transform: uppercase;
          color: var(--secondary-text-color);
          margin-bottom: 6px;
        }
        .reminder-meta-value {
          font-size: 15px;
          font-weight: 600;
          line-height: 1.35;
          word-break: break-word;
        }
        .meta-compact {
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }
        .reminder-timer-block {
          display: flex;
          flex-direction: column;
          gap: 10px;
          padding: 14px;
          border-radius: 14px;
          background: color-mix(in srgb, var(--primary-background-color) 68%, transparent);
          border: 1px solid rgba(127, 127, 127, 0.12);
        }
        .reminder-timer-label {
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.05em;
          text-transform: uppercase;
          color: var(--secondary-text-color);
        }
        .empty-state {
          padding: 28px;
          border-radius: 18px;
          border: 1px dashed rgba(127, 127, 127, 0.25);
          color: var(--secondary-text-color);
          text-align: center;
          background: color-mix(in srgb, var(--primary-background-color) 60%, transparent);
        }
        @media (max-width: 880px) {
          :host {
            padding: 10px;
          }
          .tabs {
            flex-wrap: nowrap;
            overflow-x: auto;
            overflow-y: hidden;
            padding-bottom: 6px;
            -webkit-overflow-scrolling: touch;
          }
          .tab {
            flex: 0 0 auto;
            white-space: nowrap;
          }
          .header {
            flex-direction: row;
            align-items: center;
            gap: 10px;
            margin-bottom: 16px;
          }
          .header-main,
          .header-actions {
            width: auto;
          }
          .header-main {
            flex: 1;
            min-width: 0;
            justify-content: flex-start;
          }
          .header-actions {
            justify-content: flex-end;
            flex-shrink: 0;
          }
          .back-button {
            display: inline-flex;
          }
          h1 {
            font-size: 20px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }
          .reminder-title {
            font-size: 21px;
          }
          .reminder-message {
            font-size: 15px;
          }
          .reminder-meta-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 8px;
          }
          .reminder-card {
            padding: 14px;
            gap: 12px;
            border-radius: 14px;
          }
          .reminder-meta-card {
            padding: 9px 10px;
          }
          .reminder-meta-value {
            font-size: 13px;
          }
          .countdown {
            font-size: 18px;
          }
          .reminder-timer-block {
            padding: 12px;
          }
          .reminder-actions {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 8px;
          }
          .reminder-actions button,
          .reminder-actions .snooze-wrapper {
            width: 100%;
          }
          .snooze-wrapper {
            display: grid;
            grid-template-columns: minmax(0, 1fr);
            gap: 6px;
          }
          .snooze-wrapper select {
            width: 100%;
          }
        }
        @media (max-width: 420px) {
          .reminder-meta-grid {
            grid-template-columns: 1fr;
          }
        }
        @media (min-width: 800px) {
          .reminders-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            align-items: start;
          }
        }
      </style>
      
      <div class="header">
        <div class="header-main">
          <button id="btn-back" class="button-secondary back-button" type="button">Inapoi</button>
          <h1>Reminder Manager</h1>
        </div>
        <div class="header-actions">
          <button id="btn-show-add" type="button">Adauga reminder</button>
        </div>
      </div>

      <div id="reminder-form" class="card">
        <h2 id="form-title">Adauga Reminder Nou</h2>
        <div class="form-group">
          <label>Nume reminder</label>
          <input type="text" id="input-title" required>
        </div>
        <div class="form-group">
          <label>Mesaj notificare</label>
          <input type="text" id="input-message" required>
        </div>

        <div class="form-group">
          <label>Cand se declanseaza</label>
          <select id="input-trigger-type">
            <option value="time">Doar timp</option>
            <option value="location">Doar locatie</option>
            <option value="time_and_location">Dupa o data, la o locatie</option>
          </select>
          <div class="field-help">Pentru "Dupa o data, la o locatie": ex. "dupa 20 iunie, cand ajung la X".</div>
        </div>

        <div id="time-trigger-fields">
          <div class="form-group">
            <label>Tip reminder</label>
            <select id="input-mode">
              <option value="duration">dupa durata</option>
              <option value="datetime">la data si ora</option>
            </select>
          </div>

          <div id="duration-fields">
            <div class="form-group">
              <label>Zile</label>
              <input type="number" id="input-days" value="0" min="0">
            </div>
            <div class="form-group">
              <label>Ore</label>
              <input type="number" id="input-hours" value="0" min="0">
            </div>
            <div class="form-group">
              <label>Minute</label>
              <input type="number" id="input-minutes" value="10" min="0">
            </div>
          </div>

          <div id="datetime-fields" style="display:none; gap:16px;">
            <div class="form-group" style="flex:1;">
              <label>Data</label>
              <input type="date" id="input-date">
            </div>
            <div class="form-group" style="flex:1;">
              <label>Ora</label>
              <input type="time" id="input-time">
            </div>
          </div>

          <div class="form-group">
            <label>Repetare</label>
            <select id="input-repeat">
              <option value="none">fara repetare</option>
              <option value="monthly">lunar la aceeasi data si ora</option>
            </select>
            <div class="field-help">Repetarea lunara functioneaza pentru remindere setate la data si ora fixa. Daca o luna are mai putine zile, reminderul ruleaza in ultima zi disponibila.</div>
          </div>
        </div>

        <div id="location-trigger-fields" style="display:none;">
          <div class="form-group">
            <label>Sursa zonei</label>
            <select id="input-zone-source">
              <option value="ha_zone">Zona existenta din Home Assistant</option>
              <option value="custom">Locatie noua (lat/lon)</option>
            </select>
          </div>

          <div id="ha-zone-fields">
            <div class="form-group">
              <label>Zona</label>
              <select id="input-zone-entity"></select>
              <div class="field-help">Zonele se gestioneaza din Settings &rarr; Areas, Zones &amp; Labels &rarr; Zones.</div>
            </div>
          </div>

          <div id="custom-zone-fields" style="display:none;">
            <div class="form-group">
              <label>Nume locatie</label>
              <input type="text" id="input-custom-zone-name" placeholder="ex. Auchan Vitan">
            </div>

            <div class="form-group">
              <button type="button" id="btn-toggle-map" class="button-secondary">Alege pe harta</button>
              <div class="field-help">Apasa "Alege pe harta", apoi click oriunde pentru a pune pinul. Poti trage si pinul.</div>
            </div>

            <div id="map-picker-wrapper" style="display:none;">
              <div id="map-picker" style="height:340px;border-radius:12px;overflow:hidden;border:1px solid rgba(127,127,127,0.2);margin-bottom:8px;"></div>
              <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap;">
                <button type="button" id="btn-use-map">Foloseste locatia</button>
                <button type="button" id="btn-close-map" class="button-secondary">Inchide harta</button>
                <span id="map-coord-readout" class="field-help" style="margin:0;"></span>
              </div>
            </div>

            <div class="form-group">
              <label>Latitudine</label>
              <input type="number" step="0.000001" id="input-custom-zone-lat" placeholder="44.426300">
            </div>
            <div class="form-group">
              <label>Longitudine</label>
              <input type="number" step="0.000001" id="input-custom-zone-lon" placeholder="26.148700">
            </div>
            <div class="form-group">
              <label>Raza (metri)</label>
              <input type="number" id="input-custom-zone-radius" value="150" min="1" max="50000">
              <div class="field-help">Cercul de pe harta se actualizeaza pe baza acestei valori.</div>
            </div>
          </div>

          <div class="form-group">
            <label>Eveniment</label>
            <select id="input-zone-event">
              <option value="enter">Cand ajung in zona</option>
              <option value="leave">Cand plec din zona</option>
            </select>
          </div>

          <div class="form-group">
            <label><input type="checkbox" id="input-location-recurring"> Reminder recurent (se reaprinde la fiecare intrare/iesire)</label>
            <div class="field-help">Fara aceasta optiune, reminderul se declanseaza o singura data si trece in "Expirate".</div>
          </div>
        </div>

        <div id="active-window-fields" style="display:none;">
          <div class="form-group">
            <label>Activ incepand cu (optional)</label>
            <input type="datetime-local" id="input-active-from">
            <div class="field-help">Inainte de aceasta data reminderul nu se declanseaza chiar daca esti in zona.</div>
          </div>
          <div class="form-group">
            <label>Activ pana la (optional)</label>
            <input type="datetime-local" id="input-active-until">
            <div class="field-help">Dupa aceasta data reminderul expira automat.</div>
          </div>
        </div>

        <div class="form-group">
          <label>Utilizatori reminder</label>
          <select id="input-users" multiple size="4"></select>
          <div class="field-help">Daca selectezi mai multi utilizatori, se creeaza remindere separate si independente pentru fiecare.</div>
        </div>

        <div id="notify-targets-group" class="form-group">
          <label>Dispozitive pentru notificare</label>
          <select id="input-notify-targets" multiple size="5"></select>
          <div class="field-help">Selecteaza unul sau mai multe servicii notify.mobile_app_* pentru acest reminder.</div>
        </div>

        <div class="form-group">
          <label><input type="checkbox" id="input-mobile" checked> Notificare telefon</label>
          <label><input type="checkbox" id="input-persistent" checked> Notificare Home Assistant (globala)</label>
          <div class="field-help">Cand notificarea pe telefon este activa, Reminder Manager trimite un prim preaviz cu sunet la T-5 minute, apoi actualizari silențioase pe acelasi tag, cu butoane Done/Snooze. Notificarea Home Assistant este globala.</div>
        </div>

        <div style="display: flex; gap: 8px;">
          <button id="btn-save">Salveaza</button>
          <button id="btn-cancel" class="button-secondary">Anuleaza</button>
        </div>
      </div>

      <div class="tabs">
        <div class="tab active" data-tab="active">Remindere active</div>
        <div class="tab" data-tab="expired">Remindere expirate</div>
        <div class="tab" data-tab="done">Finalizate</div>
      </div>

      <div id="reminders-container"></div>
    `;

    this.shadowRoot.getElementById("btn-back").addEventListener("click", () => {
      this.goBack();
    });

    this.shadowRoot.getElementById("btn-show-add").addEventListener("click", () => {
      this.openForm();
    });

    this.shadowRoot.getElementById("btn-cancel").addEventListener("click", () => {
      this.shadowRoot.getElementById("reminder-form").style.display = "none";
    });

    this.shadowRoot.getElementById("input-mode").addEventListener("change", (e) => {
      this.setMode(e.target.value);
    });
    this.shadowRoot.getElementById("input-mobile").addEventListener("change", () => {
      this.toggleNotifyTargetGroup();
    });
    this.shadowRoot.getElementById("input-trigger-type").addEventListener("change", (e) => {
      this.setTriggerType(e.target.value);
    });
    this.shadowRoot.getElementById("input-zone-source").addEventListener("change", (e) => {
      this.setZoneSource(e.target.value);
    });
    this.shadowRoot.getElementById("btn-toggle-map").addEventListener("click", () => this.openMapPicker());
    this.shadowRoot.getElementById("btn-close-map").addEventListener("click", () => this.closeMapPicker());
    this.shadowRoot.getElementById("btn-use-map").addEventListener("click", () => this.applyMapLocation());
    this.shadowRoot.getElementById("input-custom-zone-radius").addEventListener("input", () => this.refreshMapRadius());

    this.shadowRoot.getElementById("btn-save").addEventListener("click", () => this.saveReminder());

    this.shadowRoot.querySelectorAll(".tab").forEach(tab => {
      tab.addEventListener("click", (e) => {
        this.shadowRoot.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
        e.target.classList.add("active");
        this.currentTab = e.target.dataset.tab;
        this.renderReminders();
      });
    });

    this.currentTab = "active";
    this.renderRecipientOptions();
    this.toggleNotifyTargetGroup();
  }

  setMode(mode) {
    this.shadowRoot.getElementById("input-mode").value = mode;
    this.shadowRoot.getElementById("duration-fields").style.display = mode === "duration" ? "block" : "none";
    this.shadowRoot.getElementById("datetime-fields").style.display = mode === "datetime" ? "flex" : "none";
    const repeat = this.shadowRoot.getElementById("input-repeat");
    if (repeat) {
      repeat.disabled = mode !== "datetime";
      if (mode !== "datetime") {
        repeat.value = "none";
      }
    }
  }

  setTriggerType(triggerType) {
    this.shadowRoot.getElementById("input-trigger-type").value = triggerType;
    const timeBlock = this.shadowRoot.getElementById("time-trigger-fields");
    const locBlock = this.shadowRoot.getElementById("location-trigger-fields");
    const activeBlock = this.shadowRoot.getElementById("active-window-fields");
    timeBlock.style.display = triggerType === "time" ? "block" : "none";
    locBlock.style.display = (triggerType === "location" || triggerType === "time_and_location") ? "block" : "none";
    activeBlock.style.display = (triggerType === "location" || triggerType === "time_and_location") ? "block" : "none";
  }

  setZoneSource(source) {
    this.shadowRoot.getElementById("input-zone-source").value = source;
    this.shadowRoot.getElementById("ha-zone-fields").style.display = source === "ha_zone" ? "block" : "none";
    this.shadowRoot.getElementById("custom-zone-fields").style.display = source === "custom" ? "block" : "none";
  }

  async _loadLeaflet() {
    if (window.L) return window.L;
    if (!ReminderManagerPanel._leafletPromise) {
      const cssUrl = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      const jsUrl = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
      ReminderManagerPanel._leafletPromise = (async () => {
        const css = await fetch(cssUrl).then((r) => r.text());
        ReminderManagerPanel._leafletCss = css;
        await new Promise((resolve, reject) => {
          if (document.querySelector(`script[data-rm-leaflet]`)) {
            const wait = () => (window.L ? resolve() : setTimeout(wait, 50));
            return wait();
          }
          const s = document.createElement("script");
          s.src = jsUrl;
          s.dataset.rmLeaflet = "1";
          s.onload = resolve;
          s.onerror = () => reject(new Error("Nu s-a putut incarca Leaflet (verifica internetul)."));
          document.head.appendChild(s);
        });
        return window.L;
      })();
    }
    return ReminderManagerPanel._leafletPromise;
  }

  _injectLeafletCss() {
    if (this._leafletCssInjected) return;
    const css = ReminderManagerPanel._leafletCss;
    if (!css) return;
    const style = document.createElement("style");
    // Rewrite relative image urls so marker/layer icons load from CDN
    style.textContent = css.replace(/url\((['"]?)images\//g, `url($1https://unpkg.com/leaflet@1.9.4/dist/images/`);
    this.shadowRoot.appendChild(style);
    this._leafletCssInjected = true;
  }

  _initialMapCenter() {
    const latInput = parseFloat(this.shadowRoot.getElementById("input-custom-zone-lat").value);
    const lonInput = parseFloat(this.shadowRoot.getElementById("input-custom-zone-lon").value);
    if (!Number.isNaN(latInput) && !Number.isNaN(lonInput)) {
      return [latInput, lonInput];
    }
    if (this._hass && this._hass.config) {
      const { latitude, longitude } = this._hass.config;
      if (typeof latitude === "number" && typeof longitude === "number") {
        return [latitude, longitude];
      }
    }
    return [44.4361414, 26.102684];
  }

  _readRadius() {
    const radius = parseFloat(this.shadowRoot.getElementById("input-custom-zone-radius").value);
    if (Number.isNaN(radius) || radius <= 0) return 150;
    return Math.min(radius, 50000);
  }

  async openMapPicker() {
    const wrapper = this.shadowRoot.getElementById("map-picker-wrapper");
    wrapper.style.display = "block";
    try {
      const L = await this._loadLeaflet();
      this._injectLeafletCss();
      const center = this._initialMapCenter();
      const radius = this._readRadius();

      if (!this._map) {
        // Leaflet's default marker resolves image URLs via getComputedStyle on
        // a probe div; that fails inside a Shadow DOM, so we pin the icons to
        // the same CDN serving the CSS.
        const iconBase = "https://unpkg.com/leaflet@1.9.4/dist/images/";
        delete L.Icon.Default.prototype._getIconUrl;
        L.Icon.Default.mergeOptions({
          iconRetinaUrl: `${iconBase}marker-icon-2x.png`,
          iconUrl: `${iconBase}marker-icon.png`,
          shadowUrl: `${iconBase}marker-shadow.png`,
        });

        const container = this.shadowRoot.getElementById("map-picker");
        this._map = L.map(container, { zoomControl: true }).setView(center, 14);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution: '&copy; OpenStreetMap',
        }).addTo(this._map);

        this._marker = L.marker(center, { draggable: true }).addTo(this._map);
        this._circle = L.circle(center, { radius, color: "#03a9f4", weight: 2, fillOpacity: 0.12 }).addTo(this._map);

        this._marker.on("drag", () => {
          const { lat, lng } = this._marker.getLatLng();
          this._circle.setLatLng([lat, lng]);
          this._updateMapReadout(lat, lng);
        });
        this._map.on("click", (e) => {
          this._marker.setLatLng(e.latlng);
          this._circle.setLatLng(e.latlng);
          this._updateMapReadout(e.latlng.lat, e.latlng.lng);
        });
      } else {
        this._marker.setLatLng(center);
        this._circle.setLatLng(center).setRadius(radius);
        this._map.setView(center, this._map.getZoom() || 14);
      }
      this._updateMapReadout(center[0], center[1]);
      // Container was hidden when map was created — fix tile rendering
      setTimeout(() => this._map.invalidateSize(), 50);
    } catch (err) {
      wrapper.style.display = "none";
      alert(err.message || "Eroare la incarcarea hartii.");
    }
  }

  closeMapPicker() {
    this.shadowRoot.getElementById("map-picker-wrapper").style.display = "none";
  }

  applyMapLocation() {
    if (!this._marker) return;
    const { lat, lng } = this._marker.getLatLng();
    this.shadowRoot.getElementById("input-custom-zone-lat").value = lat.toFixed(6);
    this.shadowRoot.getElementById("input-custom-zone-lon").value = lng.toFixed(6);
    this.closeMapPicker();
  }

  refreshMapRadius() {
    if (this._circle) {
      this._circle.setRadius(this._readRadius());
    }
  }

  _updateMapReadout(lat, lng) {
    const el = this.shadowRoot.getElementById("map-coord-readout");
    if (el) {
      el.textContent = `Pin: ${lat.toFixed(6)}, ${lng.toFixed(6)} (raza ${this._readRadius()}m)`;
    }
  }

  formatDateValue(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  formatTimeValue(date) {
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    return `${hours}:${minutes}`;
  }

  getSelectedValues(elementId) {
    const element = this.shadowRoot.getElementById(elementId);
    if (!element) {
      return [];
    }
    return Array.from(element.selectedOptions).map((option) => option.value);
  }

  setSelectedValues(elementId, values) {
    const element = this.shadowRoot.getElementById(elementId);
    if (!element) {
      return;
    }

    const selected = new Set(values || []);
    Array.from(element.options).forEach((option) => {
      option.selected = selected.has(option.value);
    });
  }

  renderRecipientOptions() {
    this.renderSelectOptions("input-users", this.availableUsers, "id", "name", "Nu exista utilizatori disponibili.");
    this.renderSelectOptions("input-notify-targets", this.availableNotifyTargets, "service", "label", "Nu exista servicii notify disponibile.");
    this.renderSelectOptions("input-zone-entity", this.availableZones, "entity_id", "name", "Nu exista zone definite in Home Assistant.");
  }

  renderSelectOptions(elementId, items, valueKey, labelKey, emptyLabel) {
    const element = this.shadowRoot.getElementById(elementId);
    if (!element) {
      return;
    }

    if (!items || items.length === 0) {
      element.innerHTML = `<option value="" disabled>${emptyLabel}</option>`;
      return;
    }

    element.innerHTML = items
      .map((item) => `<option value="${item[valueKey]}">${item[labelKey]}</option>`)
      .join("");
  }

  toggleNotifyTargetGroup() {
    const mobileEnabled = this.shadowRoot.getElementById("input-mobile")?.checked;
    const group = this.shadowRoot.getElementById("notify-targets-group");
    if (group) {
      group.style.display = mobileEnabled ? "block" : "none";
    }
  }

  getDefaultTargetUserIds() {
    return this.currentUser ? [this.currentUser.id] : [];
  }

  formatUserNames(userIds) {
    if (!userIds || userIds.length === 0) {
      return "shared";
    }

    return userIds.map((userId) => {
      const match = this.availableUsers.find((user) => user.id === userId);
      return match ? match.name : userId;
    }).join(", ");
  }

  formatNotifyTargets(targets) {
    if (!targets || targets.length === 0) {
      return "fallback global";
    }

    return targets.map((target) => {
      const match = this.availableNotifyTargets.find((item) => item.service === target);
      return match ? match.label : target;
    }).join(", ");
  }

  formatRepeatLabel(repeat) {
    return repeat === "monthly" ? "Lunar" : "O singura data";
  }

  formatLocationSummary(reminder) {
    if (reminder.custom_zone && reminder.custom_zone.name) {
      const radius = reminder.custom_zone.radius != null ? `, ${reminder.custom_zone.radius}m` : "";
      return `${reminder.custom_zone.name}${radius}`;
    }
    if (reminder.zone_entity_id) {
      const match = this.availableZones.find((z) => z.entity_id === reminder.zone_entity_id);
      return match ? match.name : reminder.zone_entity_id;
    }
    return "fara zona";
  }

  formatZoneEventLabel(reminder) {
    const event = reminder.zone_event === "leave" ? "Cand plec" : "Cand ajung";
    return reminder.location_recurring ? `${event} (recurent)` : event;
  }

  escapeAttribute(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("\"", "&quot;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  formatStatusLabel(status) {
    if (status === "active") return "Activ";
    if (status === "expired") return "Expirat";
    if (status === "done") return "Finalizat";
    return status || "Necunoscut";
  }

  formatDurationParts(totalSeconds) {
    const seconds = Math.max(0, Math.floor(totalSeconds));
    const units = [
      { size: 30 * 24 * 60 * 60, singular: "luna", plural: "luni" },
      { size: 24 * 60 * 60, singular: "zi", plural: "zile" },
      { size: 60 * 60, singular: "ora", plural: "ore" },
      { size: 60, singular: "minut", plural: "minute" },
      { size: 1, singular: "secunda", plural: "secunde" }
    ];

    let remaining = seconds;
    const parts = [];

    units.forEach((unit) => {
      if (parts.length >= 2) {
        return;
      }

      const amount = Math.floor(remaining / unit.size);
      if (amount <= 0) {
        return;
      }

      parts.push(`${amount} ${amount === 1 ? unit.singular : unit.plural}`);
      remaining -= amount * unit.size;
    });

    return parts.length > 0 ? parts.join(" ") : "0 secunde";
  }

  getFallbackBackPath() {
    if (this._hass && typeof this._hass.hassUrl === "function") {
      return this._hass.hassUrl("/");
    }
    return "/";
  }

  goBack() {
    const currentPath = window.location.pathname;
    if (window.history.length > 1) {
      window.history.back();
      window.setTimeout(() => {
        if (window.location.pathname === currentPath) {
          window.location.assign(this.getFallbackBackPath());
        }
      }, 180);
      return;
    }

    window.location.assign(this.getFallbackBackPath());
  }

  openForm(reminder = null) {
    this.editingId = reminder ? reminder.id : null;
    this.shadowRoot.getElementById("form-title").textContent = reminder ? "Editeaza Reminder" : "Adauga Reminder Nou";

    this.shadowRoot.getElementById("input-title").value = reminder ? reminder.title : "";
    this.shadowRoot.getElementById("input-message").value = reminder ? reminder.message : "";
    this.shadowRoot.getElementById("input-mobile").checked = reminder ? reminder.notify_mobile : true;
    this.shadowRoot.getElementById("input-persistent").checked = reminder ? reminder.notify_persistent : true;

    this.setMode("duration");

    this.shadowRoot.getElementById("input-days").value = "0";
    this.shadowRoot.getElementById("input-hours").value = "0";
    this.shadowRoot.getElementById("input-minutes").value = "10";
    this.shadowRoot.getElementById("input-date").value = "";
    this.shadowRoot.getElementById("input-time").value = "";
    this.shadowRoot.getElementById("input-repeat").value = reminder ? (reminder.repeat || "none") : "none";
    this.setSelectedValues("input-users", reminder ? (reminder.target_user_ids || []) : this.getDefaultTargetUserIds());
    this.setSelectedValues("input-notify-targets", reminder ? (reminder.notify_targets || []) : []);
    this.toggleNotifyTargetGroup();

    // Trigger type + location fields
    const triggerType = (reminder && reminder.trigger_type) || "time";
    this.setTriggerType(triggerType);

    const zoneSource = reminder && reminder.custom_zone ? "custom" : "ha_zone";
    this.setZoneSource(zoneSource);
    this.shadowRoot.getElementById("input-zone-entity").value =
      reminder && reminder.zone_entity_id ? reminder.zone_entity_id : "";
    const customZone = (reminder && reminder.custom_zone) || {};
    this.shadowRoot.getElementById("input-custom-zone-name").value = customZone.name || "";
    this.shadowRoot.getElementById("input-custom-zone-lat").value =
      customZone.latitude != null ? customZone.latitude : "";
    this.shadowRoot.getElementById("input-custom-zone-lon").value =
      customZone.longitude != null ? customZone.longitude : "";
    this.shadowRoot.getElementById("input-custom-zone-radius").value =
      customZone.radius != null ? customZone.radius : 150;
    this.shadowRoot.getElementById("input-zone-event").value =
      (reminder && reminder.zone_event) || "enter";
    this.shadowRoot.getElementById("input-location-recurring").checked =
      !!(reminder && reminder.location_recurring);

    this.shadowRoot.getElementById("input-active-from").value =
      reminder && reminder.active_from ? this.formatDateTimeLocalValue(new Date(reminder.active_from)) : "";
    this.shadowRoot.getElementById("input-active-until").value =
      reminder && reminder.active_until ? this.formatDateTimeLocalValue(new Date(reminder.active_until)) : "";

    if (reminder && reminder.target_time && triggerType === "time") {
      const targetTime = new Date(reminder.target_time);
      if (!Number.isNaN(targetTime.getTime())) {
        this.setMode("datetime");
        this.shadowRoot.getElementById("input-date").value = this.formatDateValue(targetTime);
        this.shadowRoot.getElementById("input-time").value = this.formatTimeValue(targetTime);
      }
    }

    this.shadowRoot.getElementById("reminder-form").style.display = "block";
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  formatDateTimeLocalValue(date) {
    if (!date || Number.isNaN(date.getTime())) return "";
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  saveReminder() {
    const title = this.shadowRoot.getElementById("input-title").value;
    const message = this.shadowRoot.getElementById("input-message").value;
    const triggerType = this.shadowRoot.getElementById("input-trigger-type").value;
    const mode = this.shadowRoot.getElementById("input-mode").value;
    const mobile = this.shadowRoot.getElementById("input-mobile").checked;
    const persistent = this.shadowRoot.getElementById("input-persistent").checked;
    const targetUserIds = this.getSelectedValues("input-users");
    const notifyTargets = this.getSelectedValues("input-notify-targets");

    if (!title || !message) {
      alert("Completati titlul si mesajul!");
      return;
    }

    if (this.availableUsers.length > 0 && targetUserIds.length === 0) {
      alert("Selectati cel putin un utilizator pentru reminder.");
      return;
    }

    if (mobile && this.availableNotifyTargets.length > 0 && notifyTargets.length === 0) {
      alert("Selectati cel putin un dispozitiv pentru notificarea pe telefon.");
      return;
    }

    const startTime = new Date();
    let targetTime = null;
    let repeat = "none";
    let repeatMetadata = { repeat_day: null, repeat_time: null };

    if (triggerType === "time") {
      targetTime = new Date();
      repeat = mode === "datetime" ? this.shadowRoot.getElementById("input-repeat").value : "none";

      if (mode === "duration") {
        const days = parseInt(this.shadowRoot.getElementById("input-days").value || "0");
        const hours = parseInt(this.shadowRoot.getElementById("input-hours").value || "0");
        const mins = parseInt(this.shadowRoot.getElementById("input-minutes").value || "0");
        if (days === 0 && hours === 0 && mins === 0) {
          alert("Durata trebuie sa fie mai mare decat zero!");
          return;
        }
        targetTime.setDate(targetTime.getDate() + days);
        targetTime.setHours(targetTime.getHours() + hours);
        targetTime.setMinutes(targetTime.getMinutes() + mins);
      } else {
        const dateVal = this.shadowRoot.getElementById("input-date").value;
        const timeVal = this.shadowRoot.getElementById("input-time").value;
        if (!dateVal || !timeVal) {
          alert("Selectati atat data cat si ora!");
          return;
        }
        targetTime = new Date(`${dateVal}T${timeVal}`);
        if (targetTime <= startTime) {
          alert("Data si ora selectate trebuie sa fie in viitor!");
          return;
        }
        repeatMetadata = {
          repeat_day: parseInt(dateVal.slice(-2), 10),
          repeat_time: `${timeVal}:00`,
        };
      }
    }

    // Location fields
    let zoneEntityId = null;
    let customZone = null;
    let zoneEvent = "enter";
    let locationRecurring = false;
    if (triggerType === "location" || triggerType === "time_and_location") {
      const zoneSource = this.shadowRoot.getElementById("input-zone-source").value;
      if (zoneSource === "ha_zone") {
        zoneEntityId = this.shadowRoot.getElementById("input-zone-entity").value;
        if (!zoneEntityId) {
          alert("Selectati o zona existenta sau treceti pe 'Locatie noua'.");
          return;
        }
      } else {
        const latVal = this.shadowRoot.getElementById("input-custom-zone-lat").value;
        const lonVal = this.shadowRoot.getElementById("input-custom-zone-lon").value;
        const radiusVal = this.shadowRoot.getElementById("input-custom-zone-radius").value;
        const nameVal = this.shadowRoot.getElementById("input-custom-zone-name").value;
        const lat = parseFloat(latVal);
        const lon = parseFloat(lonVal);
        const radius = parseFloat(radiusVal);
        if (Number.isNaN(lat) || Number.isNaN(lon)) {
          alert("Completati latitudinea si longitudinea pentru locatia noua.");
          return;
        }
        if (Number.isNaN(radius) || radius <= 0) {
          alert("Raza trebuie sa fie un numar pozitiv (metri).");
          return;
        }
        customZone = { name: nameVal, latitude: lat, longitude: lon, radius };
      }
      zoneEvent = this.shadowRoot.getElementById("input-zone-event").value;
      locationRecurring = this.shadowRoot.getElementById("input-location-recurring").checked;
    }

    const activeFromVal = this.shadowRoot.getElementById("input-active-from").value;
    const activeUntilVal = this.shadowRoot.getElementById("input-active-until").value;
    const activeFrom = activeFromVal ? new Date(activeFromVal).toISOString() : null;
    const activeUntil = activeUntilVal ? new Date(activeUntilVal).toISOString() : null;

    if (triggerType === "time_and_location" && !activeFrom) {
      alert('Pentru "Dupa o data, la o locatie" trebuie sa setezi "Activ incepand cu".');
      return;
    }
    if (activeFrom && activeUntil && new Date(activeFrom) >= new Date(activeUntil)) {
      alert('"Activ incepand cu" trebuie sa fie inainte de "Activ pana la".');
      return;
    }

    const corePayload = {
      title,
      message,
      trigger_type: triggerType,
      target_time: targetTime ? targetTime.toISOString() : null,
      repeat,
      ...repeatMetadata,
      notify_mobile: mobile,
      notify_persistent: persistent,
      target_user_ids: targetUserIds.length > 0 ? targetUserIds : this.getDefaultTargetUserIds(),
      notify_targets: notifyTargets,
      zone_entity_id: zoneEntityId,
      custom_zone: customZone,
      zone_event: zoneEvent,
      location_recurring: locationRecurring,
      active_from: activeFrom,
      active_until: activeUntil,
    };

    if (this.editingId) {
      this.performAction("update", {
        id: this.editingId,
        updates: {
          ...corePayload,
          status: "active",
          notified: false,
          pre_notified: false,
          pre_notification_bucket: null,
          location_triggered: false,
          last_in_zone: false,
        },
      });
    } else {
      const reminder = {
        ...corePayload,
        start_time: startTime.toISOString(),
        status: "active",
        notified: false,
        pre_notified: false,
        pre_notification_bucket: null,
        location_triggered: false,
        last_in_zone: false,
      };
      this.performAction("add", { reminder });
    }

    this.shadowRoot.getElementById("reminder-form").style.display = "none";
  }

  renderReminders() {
    const container = this.shadowRoot.getElementById("reminders-container");
    container.innerHTML = "";
    container.className = "";

    const filtered = this.reminders.filter(r => {
      if (this.currentTab === "active") return r.status === "active";
      if (this.currentTab === "expired") return r.status === "expired";
      if (this.currentTab === "done") return r.status === "done";
      return true;
    });

    if (filtered.length === 0) {
      container.innerHTML = `<div class="empty-state">Nu exista remindere in aceasta categorie.</div>`;
      return;
    }

    container.className = "reminders-grid";

    filtered.forEach(r => {
      const card = document.createElement("div");
      card.className = `reminder-card status-${r.status}`;

      const triggerType = r.trigger_type || "time";
      const isTimeTrigger = triggerType === "time";
      const statusLabel = this.formatStatusLabel(r.status);

      const primaryMetaLabel = isTimeTrigger ? "Tinta" : "Locatie";
      const primaryMetaValue = isTimeTrigger
        ? new Date(r.target_time).toLocaleString()
        : this.formatLocationSummary(r);
      const secondaryMetaLabel = isTimeTrigger ? "Repetare" : "Eveniment";
      const secondaryMetaValue = isTimeTrigger
        ? this.formatRepeatLabel(r.repeat)
        : this.formatZoneEventLabel(r);

      let html = `
        <div class="reminder-card-header">
          <div class="reminder-status-badge status-badge-${r.status}">${statusLabel}</div>
          <div class="reminder-title">${r.title}</div>
          <div class="reminder-message">${r.message}</div>
        </div>
        <div class="reminder-meta-grid">
          <div class="reminder-meta-card">
            <div class="reminder-meta-label">${primaryMetaLabel}</div>
            <div class="reminder-meta-value meta-compact" title="${this.escapeAttribute(primaryMetaValue)}">${primaryMetaValue}</div>
          </div>
          <div class="reminder-meta-card">
            <div class="reminder-meta-label">${secondaryMetaLabel}</div>
            <div class="reminder-meta-value">${secondaryMetaValue}</div>
          </div>
          <div class="reminder-meta-card">
            <div class="reminder-meta-label">Utilizatori</div>
            <div class="reminder-meta-value meta-compact" title="${this.escapeAttribute(this.formatUserNames(r.target_user_ids))}">${this.formatUserNames(r.target_user_ids)}</div>
          </div>
          <div class="reminder-meta-card">
            <div class="reminder-meta-label">Dispozitive</div>
            <div class="reminder-meta-value meta-compact" title="${this.escapeAttribute(this.formatNotifyTargets(r.notify_targets))}">${this.formatNotifyTargets(r.notify_targets)}</div>
          </div>
        </div>
      `;

      if (!isTimeTrigger && (r.active_from || r.active_until)) {
        const fromStr = r.active_from ? new Date(r.active_from).toLocaleString() : "imediat";
        const untilStr = r.active_until ? new Date(r.active_until).toLocaleString() : "fara expirare";
        html += `<div class="reminder-meta-card"><div class="reminder-meta-label">Fereastra activa</div><div class="reminder-meta-value">${fromStr} &rarr; ${untilStr}</div></div>`;
      }

      if (isTimeTrigger && (r.status === "active" || r.status === "expired")) {
        html += `
          <div class="reminder-timer-block">
            <div class="reminder-timer-label">Timp</div>
            <div class="countdown" id="cd-${r.id}"></div>
            <div class="progress-bar-container">
              <div class="progress-bar" id="pb-${r.id}"></div>
            </div>
          </div>
        `;
      }

      html += `<div class="reminder-actions">`;
      
      if (r.status !== "done") {
        html += `<button class="btn-done" data-id="${r.id}">Done</button>`;
      }
      
      if (isTimeTrigger && (r.status === "active" || r.status === "expired")) {
        html += `
          <div class="snooze-wrapper">
            <select id="snooze-select-${r.id}">
              <option value="10m">10 minute</option>
              <option value="1h">1 ora</option>
              <option value="1d">maine</option>
              <option value="7d">7 zile</option>
            </select>
            <button class="btn-snooze button-secondary" data-id="${r.id}">Snooze</button>
          </div>
        `;
      }
      
      html += `<button class="btn-edit button-secondary" data-id="${r.id}">Edit</button>`;
      html += `<button class="btn-delete button-danger" data-id="${r.id}">Delete</button>`;
      
      html += `</div>`;
      card.innerHTML = html;
      container.appendChild(card);
    });

    this.shadowRoot.querySelectorAll(".btn-done").forEach(btn => {
      btn.addEventListener("click", (e) => {
        this.performAction("done", { id: e.target.dataset.id });
      });
    });

    this.shadowRoot.querySelectorAll(".btn-edit").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const id = e.target.dataset.id;
        const r = this.reminders.find(x => x.id === id);
        if (r) this.openForm(r);
      });
    });

    this.shadowRoot.querySelectorAll(".btn-snooze").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const id = e.target.dataset.id;
        const r = this.reminders.find(x => x.id === id);
        const sel = this.shadowRoot.getElementById(`snooze-select-${id}`).value;
        if (r) {
          const newTarget = new Date();
          if (sel === "10m") newTarget.setMinutes(newTarget.getMinutes() + 10);
          if (sel === "1h") newTarget.setHours(newTarget.getHours() + 1);
          if (sel === "1d") newTarget.setDate(newTarget.getDate() + 1);
          if (sel === "7d") newTarget.setDate(newTarget.getDate() + 7);

          this.performAction("update", { 
            id, 
            updates: { 
              target_time: newTarget.toISOString(),
              start_time: new Date().toISOString(),
              status: "active",
              notified: false
            } 
          });
        }
      });
    });

    this.shadowRoot.querySelectorAll(".btn-delete").forEach(btn => {
      btn.addEventListener("click", (e) => {
        if(confirm("Esti sigur ca vrei sa stergi acest reminder?")) {
          this.performAction("delete", { id: e.target.dataset.id });
        }
      });
    });

    this.updateTimers();
  }

  updateTimers() {
    const now = new Date();
    this.reminders.forEach(r => {
      if (r.status !== "active" && r.status !== "expired") return;
      if ((r.trigger_type || "time") !== "time") return;
      if (!r.target_time) return;

      const cdEl = this.shadowRoot.getElementById("cd-" + r.id);
      const pbEl = this.shadowRoot.getElementById("pb-" + r.id);

      if (!cdEl || !pbEl) return;

      const start = new Date(r.start_time);
      const target = new Date(r.target_time);
      const total = target - start;
      const elapsed = now - start;
      const remaining = target - now;

      if (remaining <= 0) {
        cdEl.textContent = `Expirat de ${this.formatDurationParts(Math.abs(remaining) / 1000)}`;
        cdEl.style.color = "var(--error-color, red)";
        pbEl.style.width = "100%";
        pbEl.className = "progress-bar red";
      } else {
        cdEl.textContent = `${this.formatDurationParts(remaining / 1000)} ramase`;
        cdEl.style.color = "";

        let percent = (elapsed / total) * 100;
        if (percent < 0) percent = 0;
        if (percent > 100) percent = 100;
        pbEl.style.width = `${percent}%`;

        if (remaining < 60 * 60 * 1000) {
          pbEl.className = "progress-bar red";
        } else if (remaining < 24 * 60 * 60 * 1000) {
          pbEl.className = "progress-bar yellow";
        } else {
          pbEl.className = "progress-bar";
        }
      }
    });
  }

  disconnectedCallback() {
    if (this.intervalId) clearInterval(this.intervalId);
    if (this.syncIntervalId) clearInterval(this.syncIntervalId);
  }
}

customElements.define("reminder-manager-panel", ReminderManagerPanel);
