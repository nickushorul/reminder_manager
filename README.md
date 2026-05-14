# Reminder Manager pentru Home Assistant

Un sistem personal de remindere nelimitate, gestionate complet din interfata Home Assistant, fara YAML pentru utilizare zilnica.

Repository GitHub:
`https://github.com/nickushorul/reminder_manager`

## Instalare prin HACS
1. Deschide HACS si mergi la `Custom repositories`.
2. Adauga repository-ul:
   `https://github.com/nickushorul/reminder_manager`
3. Alege tipul `Integration`.
4. Instaleaza `Reminder Manager` din HACS.
5. Restarteaza Home Assistant.
6. Mergi la `Settings -> Devices & Services`.
7. Apasa `Add Integration` si cauta `Reminder Manager`.

Important:
- acest repository trebuie adaugat ca `Integration`, nu ca `Plugin`
- structura repository-ului este pentru `custom_components/reminder_manager`

## Configurare initiala
1. Dupa adaugarea integrarii, verifica daca apare `Reminder Manager` in sidebar.
2. La creare sau editare, alege pentru fiecare reminder:
   - utilizatorul sau utilizatorii care trebuie sa il vada
   - dispozitivul sau dispozitivele `notify.mobile_app_*` care trebuie sa primeasca notificarea
   - daca reminderul trebuie sa ruleze o singura data sau lunar la aceeasi data si ora
3. Pentru reminderele cu notificare mobila activa, componenta trimite automat un prim preaviz mobil cu sunet cand reminderul intra in ultimele 5 minute, apoi actualizari silențioase pe acelasi `tag`.
4. Optiunea globala `notify_service` ramane doar fallback pentru remindere vechi sau pentru cazurile in care nu exista targete explicite pe reminder.

## Test rapid recomandat
1. Creeaza un reminder peste 1 minut.
2. Verifica daca apare in lista si daca countdown-ul scade.
3. Verifica notificarea mobila si notificarea persistenta.
4. Verifica preavizul mobil din ultimele 5 minute si butoanele `Done` / `Snooze`.
5. Testeaza `Delete`.
6. Creeaza un reminder lunar si verifica daca dupa expirare apare automat urmatoarea aparitie pentru luna urmatoare.
7. Restarteaza Home Assistant si verifica daca reminderul ramane salvat.

## Instalare manuala
1. Copiaza folderul `custom_components/reminder_manager` in:
   `/config/custom_components/reminder_manager`
2. Restarteaza Home Assistant.
3. Adauga integrarea din `Settings -> Devices & Services`.

## Update componenta
Pentru utilizatori:
1. Deschide HACS.
2. Daca apare `Pending update`, apasa `Update` sau `Redownload`.
3. Restarteaza Home Assistant dupa update.

Pentru dezvoltare/publicare:
1. Modifica codul.
2. Creste `version` in `custom_components/reminder_manager/manifest.json`.
3. Commit + push pe `main`.
4. Creeaza un GitHub Release, de exemplu `v1.2.0`.
5. In repository-ul GitHub, adauga topic-uri pentru HACS, de exemplu:
   `home-assistant`, `home-assistant-integration`, `hacs`, `reminder`

Cum functioneaza:
- daca publici GitHub Releases, HACS foloseste release-ul cel mai nou pentru versiune si update-uri
- daca nu publici release-uri, HACS foloseste branch-ul default si versiunea remota va fi bazata pe commit
- workflow-urile GitHub Actions din `.github/workflows/` valideaza structura HACS si integrarea Home Assistant
