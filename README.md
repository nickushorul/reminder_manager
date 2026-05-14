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
1. Dupa adaugarea integrarii, seteaza serviciul de notificare pentru telefon.
2. Exemplu:
   `notify.mobile_app_iphone`
3. Verifica daca apare `Reminder Manager` in sidebar.

## Test rapid recomandat
1. Creeaza un reminder peste 1 minut.
2. Verifica daca apare in lista si daca countdown-ul scade.
3. Verifica notificarea mobila si notificarea persistenta.
4. Testeaza `Snooze`, `Done` si `Delete`.
5. Restarteaza Home Assistant si verifica daca reminderul ramane salvat.

## Instalare manuala
1. Copiaza folderul `custom_components/reminder_manager` in:
   `/config/custom_components/reminder_manager`
2. Restarteaza Home Assistant.
3. Adauga integrarea din `Settings -> Devices & Services`.
