class ReminderManagerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.reminders = [];
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
      const response = await this._hass.fetchWithAuth("/api/reminder_manager");
      if (response.ok) {
        this.reminders = await response.json();
        this.renderReminders();
      }
    } catch (err) {
      console.error("Error fetching reminders", err);
    }
  }

  async performAction(action, payload) {
    try {
      await this._hass.fetchWithAuth("/api/reminder_manager", {
        method: "POST",
        body: JSON.stringify({ action, ...payload })
      });
      this.fetchData();
    } catch (err) {
      console.error("Error performing action", action, err);
    }
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 16px;
          font-family: var(--paper-font-body1_-_font-family, sans-serif);
          background-color: var(--primary-background-color);
          color: var(--primary-text-color);
          min-height: 100vh;
        }
        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 24px;
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
        .card {
          background-color: var(--card-background-color, white);
          border-radius: 8px;
          padding: 16px;
          margin-bottom: 16px;
          box-shadow: 0 2px 4px rgba(0,0,0,0.1);
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
        .progress-bar-container {
          width: 100%;
          background-color: var(--secondary-background-color);
          border-radius: 4px;
          height: 8px;
          margin-top: 8px;
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
          margin-top: 12px;
          align-items: center;
          flex-wrap: wrap;
        }
        .reminder-title {
          font-size: 18px;
          font-weight: bold;
          margin-bottom: 4px;
        }
        .reminder-meta {
          font-size: 14px;
          color: var(--secondary-text-color);
          margin-bottom: 8px;
        }
        .countdown {
          font-weight: bold;
          font-family: monospace;
          font-size: 16px;
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
      </style>
      
      <div class="header">
        <h1>Reminder Manager</h1>
        <button id="btn-show-add">Adauga reminder</button>
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
          <label><input type="checkbox" id="input-mobile" checked> Notificare telefon</label>
          <label><input type="checkbox" id="input-persistent" checked> Notificare Home Assistant</label>
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

    this.shadowRoot.getElementById("btn-show-add").addEventListener("click", () => {
      this.openForm();
    });

    this.shadowRoot.getElementById("btn-cancel").addEventListener("click", () => {
      this.shadowRoot.getElementById("reminder-form").style.display = "none";
    });

    this.shadowRoot.getElementById("input-mode").addEventListener("change", (e) => {
      this.setMode(e.target.value);
    });

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
  }

  setMode(mode) {
    this.shadowRoot.getElementById("input-mode").value = mode;
    this.shadowRoot.getElementById("duration-fields").style.display = mode === "duration" ? "block" : "none";
    this.shadowRoot.getElementById("datetime-fields").style.display = mode === "datetime" ? "flex" : "none";
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

  openForm(reminder = null) {
    this.editingId = reminder ? reminder.id : null;
    this.shadowRoot.getElementById("form-title").textContent = reminder ? "Editeaza Reminder" : "Adauga Reminder Nou";
    
    this.shadowRoot.getElementById("input-title").value = reminder ? reminder.title : "";
    this.shadowRoot.getElementById("input-message").value = reminder ? reminder.message : "";
    this.shadowRoot.getElementById("input-mobile").checked = reminder ? reminder.notify_mobile : true;
    this.shadowRoot.getElementById("input-persistent").checked = reminder ? reminder.notify_persistent : true;

    this.shadowRoot.getElementById("input-mode").value = "duration";
    this.shadowRoot.getElementById("duration-fields").style.display = "block";
    this.shadowRoot.getElementById("datetime-fields").style.display = "none";

    this.shadowRoot.getElementById("input-days").value = "0";
    this.shadowRoot.getElementById("input-hours").value = "0";
    this.shadowRoot.getElementById("input-minutes").value = "10";
    this.shadowRoot.getElementById("input-date").value = "";
    this.shadowRoot.getElementById("input-time").value = "";

    if (reminder && reminder.target_time) {
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

  saveReminder() {
    const title = this.shadowRoot.getElementById("input-title").value;
    const message = this.shadowRoot.getElementById("input-message").value;
    const mode = this.shadowRoot.getElementById("input-mode").value;
    const mobile = this.shadowRoot.getElementById("input-mobile").checked;
    const persistent = this.shadowRoot.getElementById("input-persistent").checked;

    if (!title || !message) {
      alert("Completati titlul si mesajul!");
      return;
    }

    let targetTime = new Date();
    const startTime = new Date();

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
    }

    if (this.editingId) {
      this.performAction("update", { 
        id: this.editingId, 
        updates: { 
          title, message, target_time: targetTime.toISOString(), 
          notify_mobile: mobile, notify_persistent: persistent,
          status: "active", notified: false
        } 
      });
    } else {
      const reminder = {
        title,
        message,
        start_time: startTime.toISOString(),
        target_time: targetTime.toISOString(),
        status: "active",
        notify_mobile: mobile,
        notify_persistent: persistent,
        notified: false
      };
      this.performAction("add", { reminder });
    }

    this.shadowRoot.getElementById("reminder-form").style.display = "none";
  }

  renderReminders() {
    const container = this.shadowRoot.getElementById("reminders-container");
    container.innerHTML = "";

    const filtered = this.reminders.filter(r => {
      if (this.currentTab === "active") return r.status === "active";
      if (this.currentTab === "expired") return r.status === "expired";
      if (this.currentTab === "done") return r.status === "done";
      return true;
    });

    if (filtered.length === 0) {
      container.innerHTML = "<p>Nu exista remindere in aceasta categorie.</p>";
      return;
    }

    filtered.forEach(r => {
      const card = document.createElement("div");
      card.className = "card";
      
      const targetTime = new Date(r.target_time);
      
      let html = `
        <div class="reminder-title">${r.title}</div>
        <div class="reminder-meta">${r.message}</div>
        <div class="reminder-meta">Tinta: ${targetTime.toLocaleString()} (${r.status})</div>
      `;

      if (r.status === "active" || r.status === "expired") {
        html += `
          <div class="countdown" id="cd-${r.id}"></div>
          <div class="progress-bar-container">
            <div class="progress-bar" id="pb-${r.id}"></div>
          </div>
        `;
      }

      html += `<div class="reminder-actions">`;
      
      if (r.status !== "done") {
        html += `<button class="btn-done" data-id="${r.id}">Done</button>`;
      }
      
      if (r.status === "active" || r.status === "expired") {
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
      
      const cdEl = this.shadowRoot.getElementById("cd-" + r.id);
      const pbEl = this.shadowRoot.getElementById("pb-" + r.id);
      
      if (!cdEl || !pbEl) return;

      const start = new Date(r.start_time);
      const target = new Date(r.target_time);
      const total = target - start;
      const elapsed = now - start;
      const remaining = target - now;

      if (remaining <= 0) {
        cdEl.textContent = "Expirat!";
        cdEl.style.color = "var(--error-color, red)";
        pbEl.style.width = "100%";
        pbEl.className = "progress-bar red";
      } else {
        const d = Math.floor(remaining / (1000 * 60 * 60 * 24));
        const h = Math.floor((remaining / (1000 * 60 * 60)) % 24);
        const m = Math.floor((remaining / 1000 / 60) % 60);
        const s = Math.floor((remaining / 1000) % 60);
        
        let cdText = "";
        if (d > 0) cdText += `${d}z `;
        if (h > 0 || d > 0) cdText += `${h}h `;
        cdText += `${m}m ${s}s ramase`;
        cdEl.textContent = cdText;
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
