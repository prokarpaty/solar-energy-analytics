# Solar Energy Analytics

**EN:** Solar Energy Analytics is a self-hosted application that automatically generates solar power plant performance reports from **Home Assistant** and **sends them to your email address on a schedule**. Configure the reports once, choose which periods to receive (daily, weekly, monthly, quarterly or yearly), select a local delivery time, and the application handles collection, report generation and SMTP email delivery without requiring you to open a dashboard each day.

The application reads historical energy statistics and optional measurements from Home Assistant: solar production, household consumption, energy imported from or exported to the grid, battery charging and discharging, inverter losses and other available measurements. Each email contains an easy-to-read summary and can include the full **PDF and interactive HTML report**. Missing historical data is shown as incomplete rather than invented. The installer and report interface support **English and Ukrainian**. It is designed and verified with Deye inverters; other naming conventions may require manual sensor mapping.

**UA:** Solar Energy Analytics — це застосунок для власного сервера, який автоматично формує звіти про роботу сонячної електростанції на основі даних **Home Assistant** та **надсилає їх на електронну пошту за розкладом**. Налаштуйте застосунок один раз, оберіть періодичність звітів (щодня, щотижня, щомісяця, щокварталу або щороку) й час надсилання — після цього збір даних, формування звітів і доставлення електронною поштою виконуватимуться автоматично.

Застосунок аналізує історичну статистику та доступні показники Home Assistant: генерацію сонячної енергії, споживання будинку, імпорт і експорт електроенергії, заряд і розряд акумулятора, втрати інвертора та інші вимірювання. Лист містить зрозумілий підсумок, а до нього можуть додаватися **повний PDF-звіт та інтерактивний HTML-звіт**. Відсутні історичні дані позначаються як неповні, а не вигадуються. Майстер встановлення та звіти підтримують **українську й англійську мови**. Рішення перевірене з інверторами Deye; для інших назв датчиків може знадобитися ручне зіставлення.

### How automatic email reporting works / Як працює автоматичне надсилання звітів

| Step / Крок | English | Українська |
|---|---|---|
| 1 | Connect the app to Home Assistant using its URL and an access token. | Підключіть застосунок до Home Assistant за адресою сервера та токеном доступу. |
| 2 | Discover or map the inverter, battery, grid and consumption sensors. | Знайдіть або зіставте датчики інвертора, акумулятора, мережі та споживання. |
| 3 | Choose report types, timezone, delivery times and recipient email addresses; configure SMTP. | Оберіть типи звітів, часовий пояс, час надсилання й адреси одержувачів; налаштуйте SMTP. |
| 4 | At the scheduled time, the scheduler retrieves the completed period's historical statistics. | У запланований час планувальник отримує історичну статистику за завершений період. |
| 5 | The app creates an analytical summary, charts, an HTML report and a PDF document. | Застосунок створює аналітичний підсумок, графіки, HTML-звіт і PDF-документ. |
| 6 | The email is sent through your configured SMTP server; delivery status is recorded to avoid routine duplicates. | Лист надсилається через налаштований SMTP-сервер; статус зберігається для запобігання звичайним дублюванням. |

**EN:** Example: with daily reporting enabled at `08:00` in `Europe/Kyiv`, the application prepares the previous day's energy report and attempts SMTP delivery no earlier than 08:00, subject to statistics availability, rendering and retries. Home Assistant is the data source; the application does not control the inverter or modify its settings. Email reporting is optional: you can also generate reports locally.

**UA:** Приклад: якщо увімкнено щоденний звіт на `08:00` у часовому поясі `Europe/Kyiv`, застосунок підготує звіт за попередній день і спробує надіслати його не раніше 08:00, з урахуванням доступності статистики, створення файлів і можливих повторних спроб. Home Assistant є джерелом даних: застосунок не керує інвертором і не змінює його налаштування. Надсилання листів необов’язкове — звіти можна створювати локально.

**Status / Статус:** v1.0.0 release candidate on `main`; clean installation and production migration validated. The first automatically scheduled delivery on the migrated production version and public GitHub release publication are separate follow-up checks.

**Статус:** кандидат у реліз v1.0.0 у гілці `main`; перевірено чисте встановлення та міграцію робочого сервера. Перше автоматичне надсилання за розкладом після міграції й публікація релізу на GitHub залишаються окремими етапами.

## Example report / Приклад звіту

**EN:** Example of a daily email summary and a detailed analytical report generated automatically from Home Assistant data.

**UA:** Приклад щоденного листа з коротким підсумком та детального аналітичного звіту, автоматично сформованого за даними Home Assistant.

<img width="674" height="949" alt="1" src="https://github.com/user-attachments/assets/39c2bccd-75c0-4f48-9c83-7b03d5be144b" />
<img width="808" height="1114" alt="image" src="https://github.com/user-attachments/assets/43627dcd-fc2c-4f8d-848f-e78484fce66a" />
<img width="793" height="936" alt="image" src="https://github.com/user-attachments/assets/15fff838-640f-48ec-8a76-8ee4e61c5a50" />
<img width="803" height="1074" alt="image" src="https://github.com/user-attachments/assets/3a393d95-cc96-4633-911f-39390d443651" />

**EN:** The screenshots show the November 26, 2026 daily report with generation, consumption, grid import/export, battery charge/discharge, inverter losses and data completeness.

**UA:** На зображеннях наведено щоденний звіт за 26 листопада 2026 року: генерація, споживання, імпорт і експорт із мережі, заряд і розряд АКБ, втрати інвертора та повнота даних.

## Requirements / Вимоги

- Linux (tested with Ubuntu 24.04.5 LTS)
- Docker Engine and Docker Compose v2
- Python 3.10+ for the wizard; PyYAML and `websocket-client` (the bootstrap can offer to install missing Ubuntu/Debian packages using apt and sudo)
- Home Assistant reachable from this machine, with a dedicated long-lived access token and historical recorder statistics
- Optional SMTP account supporting STARTTLS, e.g. Gmail with a Google App Password
- At least 3 GiB free disk space for installation preflight; report storage requires additional space

**UA — вимоги:**
- Linux (перевірено на Ubuntu 24.04.5 LTS).
- Docker Engine і Docker Compose v2.
- Python 3.10+ для майстра встановлення; PyYAML і `websocket-client` (засіб початкового налаштування може запропонувати встановлення пакетів через `apt` і `sudo`).
- Доступ до Home Assistant, довготривалий токен доступу та історична статистика Recorder.
- За потреби — SMTP із підтримкою STARTTLS, наприклад Gmail із паролем застосунку Google.
- Щонайменше 3 ГіБ вільного місця для перевірки перед встановленням; для зберігання звітів знадобиться додатковий простір.

**EN:** Docker itself is not installed automatically. Run the installer as a regular user with Docker access (directly or through sudo), not as root.

**UA:** Docker не встановлюється автоматично. Запускайте майстер як звичайний користувач із доступом до Docker (безпосередньо або через sudo), а не як root.

## Install / Встановлення

### 1. Prepare Ubuntu / Підготовка Ubuntu

**EN:** On a clean Ubuntu 24.04 host, install the prerequisites for the installation wizard.

**UA:** На новому сервері Ubuntu 24.04 встановіть залежності для майстра налаштування:

```bash
sudo apt update

sudo apt install -y \
  git \
  curl \
  ca-certificates \
  python3 \
  python3-yaml \
  python3-websocket

```

### Install Docker Engine and Compose / Встановлення Docker

**EN:** On Ubuntu 24.04, install Docker Engine and the Compose v2 plugin.

**UA:** В Ubuntu 24.04 встановіть Docker Engine і плагін Compose v2:

```bash
sudo apt update

sudo apt install -y \
  docker.io \
  docker-compose-v2

sudo systemctl enable --now docker
```

**EN:** Verify the installation.

**UA:** Перевірте встановлення:

```bash
sudo docker --version
sudo docker compose version
sudo docker info --format 'Docker Engine: {{.ServerVersion}}'
```

**EN:** If `docker-compose-v2` is unavailable in Ubuntu repositories, follow the [official Docker Engine and Compose guide](https://docs.docker.com/engine/install/ubuntu/). Run the wizard as a regular user; it can use `sudo` for Docker.

**UA:** Якщо пакета `docker-compose-v2` немає в репозиторіях Ubuntu, скористайтеся [офіційною інструкцією Docker](https://docs.docker.com/engine/install/ubuntu/). Запускайте майстер як звичайний користувач — за потреби він може використовувати `sudo` для Docker.

### 2. Verify Home Assistant connectivity / Перевірка Home Assistant

**EN:** Substitute the Home Assistant server's LAN address. The example uses loopback, which only works if Home Assistant runs on the same host.

**UA:** Підставте локальну IP-адресу сервера Home Assistant. Адреса loopback у прикладі працює лише тоді, коли Home Assistant запущено на тому самому сервері.

```bash
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' \
  http://127.0.0.1:8123/api/
```

**EN:** An unauthenticated HTTP `401` confirms the API is reachable; HTTP `000` or a connection error indicates a connectivity issue. On another machine use the actual HA address, not `127.0.0.1`.

**UA:** Відповідь HTTP `401` без авторизації підтверджує доступність API; HTTP `000` або помилка з’єднання свідчить про проблему мережі. На окремому сервері використовуйте справжню адресу Home Assistant, а не `127.0.0.1`.

### 3. Clone and install / Клонування та встановлення

**EN:** Cloning over SSH requires an authorized GitHub SSH key. When the repository becomes public, HTTPS cloning can also be used.

**UA:** Для клонування через SSH потрібен авторизований SSH-ключ GitHub. Після відкриття репозиторію можна буде використовувати HTTPS.

```bash
git clone git@github.com:prokarpaty/solar-energy-analytics.git

cd solar-energy-analytics

bash install.sh
```

**EN:** Follow the English/Ukrainian wizard. It collects the Home Assistant URL and access token; discovers and maps sensors; configures power station details, equipment, branding, timezone and report language; lets you select daily, weekly, monthly, quarterly and yearly schedules and optional SMTP email delivery. It can test SMTP authentication without sending a message. The wizard validates configuration, then asks separately whether to build the Docker image and whether to start the scheduler. Do not enable a second scheduler if another installation already emails the same reports.

**UA:** Дотримуйтеся підказок двомовного майстра. Він запитує адресу Home Assistant і токен доступу, знаходить та зіставляє датчики, налаштовує дані електростанції, обладнання, оформлення, часовий пояс і мову звітів. Можна вибрати щоденні, щотижневі, щомісячні, щоквартальні та щорічні звіти, а також автоматичне надсилання через SMTP. Перевірка SMTP-автентифікації можлива без надсилання листа. Майстер перевіряє конфігурацію та окремо запитує дозвіл на побудову Docker-образу й запуск планувальника. Не запускайте другий планувальник, якщо інша інсталяція вже надсилає ті самі звіти.

### Report delivery times / Час надсилання звітів

**EN:** For each enabled report type, choose an optional local 24-hour send time, e.g. `08:00` (wizard default). The timezone comes from the wizard. Daily reports cover the previous day; weekly reports cover the previous Monday–Sunday; monthly, quarterly and yearly reports cover the previous completed calendar period. Sending starts no earlier than the later of the chosen time and the recorder-statistics delay (10 minutes by default). Collection, rendering, SMTP availability and retries can delay delivery. Changing send time does not change the period being reported.

**UA:** Для кожного увімкненого типу звіту задайте час надсилання у 24-годинному форматі, наприклад `08:00` (стандартне значення майстра). Використовується обраний часовий пояс. Щоденний звіт охоплює попередній день, щотижневий — попередній тиждень із понеділка до неділі, а щомісячний, щоквартальний і щорічний — відповідний завершений календарний період. Надсилання розпочинається не раніше вибраного часу та затримки накопичення статистики (типово 10 хвилин). Збирання даних, створення звіту, доступність SMTP і повторні спроби можуть відкласти доставлення. Зміна часу надсилання не змінює звітний період.

**EN:** For an existing installation, do not rerun the installer: edit the private `config/schedule.yaml` and add `send_time` for each desired report type.

**UA:** Для наявної інсталяції не запускайте майстер повторно: змініть приватний файл `config/schedule.yaml` і додайте `send_time` для потрібних типів звітів:

```yaml
reports:
  daily:
    enabled: true
    cron: "0 0 * * *"
    period: previous_day
    send_time: "08:00"
```

**EN:** Keep the remaining settings in `config/schedule.yaml`. Back up the file, then run `bash deploy.sh --stop` followed by `bash deploy.sh --start`. Already-queued jobs retain their dispatch/retry times, so review scheduler status before changing an active configuration.

**UA:** Збережіть інші параметри у `config/schedule.yaml`. Створіть резервну копію файлу, потім виконайте `bash deploy.sh --stop` і `bash deploy.sh --start`. Раніше створені завдання зберігають час відправлення та повторних спроб, тому перед зміною активного розкладу перевірте стан планувальника.

**EN:** Private local files are ignored by Git: `.env`, `secrets/`, `config/sensors.yaml`, `config/schedule.yaml`, `config/installation.yaml`, `reports/`, `logs/`, `state/` and `backups/`. Never commit real credentials, reports or SQLite state. The dry run previews configuration without deploying.

**UA:** Приватні локальні файли ігноруються Git: `.env`, `secrets/`, `config/sensors.yaml`, `config/schedule.yaml`, `config/installation.yaml`, `reports/`, `logs/`, `state/` і `backups/`. Ніколи не публікуйте справжні токени, паролі, звіти або базу стану SQLite. Режим попередньої перевірки показує конфігурацію без розгортання.

## Operations / Керування

```bash
bash deploy.sh --check
bash deploy.sh --build
bash deploy.sh --start
bash deploy.sh --status
bash deploy.sh --logs
bash deploy.sh --stop
```

**EN:** The release container runs without root privileges, with a read-only root filesystem, dropped Linux capabilities and a 2 GiB memory limit. It uses host networking to reach Home Assistant, so review your host firewall. The commands above respectively validate, build, start, show status, show logs and stop the scheduler.

**UA:** Контейнер працює без прав root, із файловою системою лише для читання, без додаткових можливостей Linux та з обмеженням пам’яті 2 ГіБ. Для доступу до Home Assistant використовується мережа хоста, тому перевірте налаштування брандмауера. Наведені команди відповідно перевіряють конфігурацію, будують образ, запускають сервіс, показують стан і журнали та зупиняють планувальник.

**EN:** To generate a report manually, first configure the installation and build the Docker image.

**UA:** Для ручного формування звіту спочатку налаштуйте застосунок і зберіть Docker-образ.

```bash
sudo docker compose -f compose.release.yaml -p solar-energy-analytics run --rm --no-deps solar-reports \
  python /app/scripts/generate_report.py --type daily

# Substitute the JSON filename generated above:
sudo docker compose -f compose.release.yaml -p solar-energy-analytics run --rm --no-deps solar-reports \
  python /app/scripts/render_report.py /app/reports/daily/solar-daily-YYYY-MM-DD_YYYY-MM-DD.json --language uk
```

**EN:** Each generated bundle contains the source JSON data, interactive HTML, PDF and an integrity manifest. To preview an email without sending it:

**UA:** Кожний сформований комплект містить вихідні дані JSON, інтерактивний HTML, PDF та маніфест цілісності. Щоб переглянути лист без надсилання:

```bash
sudo docker compose -f compose.release.yaml -p solar-energy-analytics run --rm --no-deps solar-reports \
  python /app/scripts/send_report.py /app/reports/daily/solar-daily-YYYY-MM-DD_YYYY-MM-DD.json --language uk --preview
```

## Backup, upgrade and rollback / Резервні копії, оновлення та відновлення

```bash
bash deploy.sh --stop
bash maintenance.sh --backup
bash maintenance.sh --upgrade
# Inspect changes and restart manually only after validation:
bash deploy.sh --check
bash deploy.sh --start
```

**EN:** `maintenance.sh --upgrade` requires a clean Git working tree and upstream branch. It stops the scheduler and creates a backup before updating the source and rebuilding the image. For rollback:

**UA:** `maintenance.sh --upgrade` потребує чистого робочого дерева Git і налаштованої віддаленої гілки. Скрипт зупиняє планувальник і створює резервну копію перед оновленням коду та побудовою образу. Для відкату:

```bash
bash deploy.sh --stop
bash maintenance.sh --rollback
bash deploy.sh --check
```

**EN:** Rollback restores the recorded Git revision and locally tagged Docker image, but **does not automatically restore** archived private configuration or scheduler state. A same-version round trip was tested; rollback between versions and database schema compatibility still need testing. Maintenance backups cover `.env`, `config/`, `secrets/` and `state/`, **not the reports directory**. Back up reports separately, encrypt backups and keep copies off-host.

**UA:** Відкат повертає збережену ревізію Git і локально позначений Docker-образ, але **не відновлює автоматично** приватну конфігурацію чи стан планувальника. Перевірено відновлення в межах тієї самої версії; сумісність схем бази даних і відкат між версіями ще потребують перевірки. Резервні копії скрипта охоплюють `.env`, `config/`, `secrets/` і `state/`, але **не каталог звітів**. Зберігайте звіти окремо, шифруйте резервні копії та тримайте додаткові копії поза сервером.

## CI and security / CI та безпека

**EN:** GitHub Actions validates shell/Python syntax and Docker Compose configuration, builds the image, runs automated tests in a restricted container and scans the image with Trivy. The pipeline blocks **fixable** HIGH/CRITICAL vulnerabilities; findings without available fixes must be reviewed separately. CI uses synthetic credentials and never deploys automatically to the home server.

**UA:** GitHub Actions перевіряє синтаксис shell/Python та конфігурацію Docker Compose, будує образ, запускає автоматизовані тести в обмеженому контейнері й сканує образ через Trivy. Конвеєр блокує **виправні** вразливості рівня HIGH/CRITICAL; проблеми, для яких ще немає виправлень, потребують окремого аналізу. У CI використовуються тестові облікові дані, а автоматичного розгортання на домашньому сервері немає.

## Limitations / Обмеження

- Historical reports depend on the availability, timestamps and completeness of Home Assistant recorder statistics. Missing historical periods are flagged rather than fabricated.
- Configured energy entities must provide compatible cumulative energy statistics. Optional equipment readings/charts vary by installation.
- SMTP acceptance is not an exactly-once guarantee. Delivery marked *unknown* should be reviewed before retrying.
- Source/configuration are bind-mounted; image-only rollback is insufficient.
- CI passing does not constitute a full security audit or a clean-room installation on another machine.
- v1.0.0 publication, cross-version upgrade/rollback validation and review of residual vulnerabilities remain release tasks.

**UA — обмеження:**
- Якість історичних звітів залежить від повноти, часових позначок і доступності статистики Home Assistant Recorder. Пропущені періоди позначаються як неповні, а не вигадуються.
- Датчики енергії мають надавати сумісні накопичувальні статистичні показники. Додаткові графіки залежать від наявного обладнання.
- Підтвердження прийняття листа SMTP не гарантує одноразової доставки. Перед повторним надсиланням перевіряйте статус *unknown*.
- Код і конфігурація підключаються до контейнера через bind mounts; відкат лише Docker-образу недостатній.
- Успішне проходження CI не означає повного аудиту безпеки або перевірки на всіх можливих системах.
- Публікація v1.0.0, перевірка оновлень і відкатів між версіями та аналіз залишкових вразливостей залишаються завданнями релізу.
