#!/usr/bin/env python3
"""Bilingual secure configuration wizard for Solar Energy Analytics.

This starter prepares configuration only. It deliberately does not deploy a
container until the original application has been safely ported and tested.
"""
from __future__ import annotations
import argparse
import getpass
import warnings
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from ha_connection import validate_url, rest_open
I18N = {
    "en": {
        "title":"SOLAR ENERGY ANALYTICS — Setup Wizard",
        "language":"Choose language / Оберіть мову: 1) English  2) Українська [1]: ",
        "welcome":"Configuration-only preview. No Docker deployment or email will occur.",
        "ha_url":"Home Assistant URL (e.g. http://192.168.1.100:8123): ",
        "ha_token":"Home Assistant long-lived access token (hidden): ",
        "timezone":"Timezone [Europe/Kyiv]: ",
        "report_language":"Report language: 1) English  2) Українська [1]: ",
        "email":"Enable SMTP email delivery? y/N: ",
        "host":"SMTP host: ",
        "port":"SMTP port [587]: ",
        "username":"SMTP username: ",
        "sender":"Sender address [same as username]: ",
        "recipient":"Recipient address: ",
        "password":"SMTP password/app password (hidden): ",
        "sensor":"Sensor mapping file [config/sensors.yaml]: ",
        "sensor_warning":"You must configure your own Home Assistant sensor entity IDs in this file before report generation.",
        "inverter":"Inverter type: 1) Deye/Sunsynk  2) Other/custom [1]: ",
        "schedule":"Enable {name} reports? [{default}]: ",
        "dryrun":"DRY RUN — no files written.",
        "exists":"Local configuration already exists. Refusing to overwrite it. Use --check to inspect safely.",
        "complete":"Configuration files created. No application has been deployed.",
        "check":"Check Home Assistant API now? y/N: ",
        "api_ok":"Home Assistant API authenticated successfully.",
        "api_fail":"Could not validate Home Assistant API: ",
        "invalid":"Invalid value: ",
        "abort":"Setup cancelled; no configuration was written.",
    },
    "uk": {
        "title":"SOLAR ENERGY ANALYTICS — Майстер налаштування",
        "language":"Choose language / Оберіть мову: 1) English  2) Українська [1]: ",
        "welcome":"Попередній майстер налаштування. Docker не запускається, листи не надсилаються.",
        "ha_url":"Адреса Home Assistant (наприклад http://192.168.1.100:8123): ",
        "ha_token":"Довготривалий токен Home Assistant (приховано): ",
        "timezone":"Часовий пояс [Europe/Kyiv]: ",
        "report_language":"Мова звітів: 1) English  2) Українська [2]: ",
        "email":"Увімкнути надсилання звітів SMTP? y/N: ",
        "host":"SMTP сервер: ",
        "port":"SMTP порт [587]: ",
        "username":"SMTP користувач: ",
        "sender":"Адреса відправника [така сама як користувач]: ",
        "recipient":"Адреса отримувача: ",
        "password":"SMTP пароль або пароль застосунку (приховано): ",
        "sensor":"Файл прив'язки датчиків [config/sensors.yaml]: ",
        "sensor_warning":"Перед генерацією звітів необхідно вказати власні ідентифікатори сутностей Home Assistant.",
        "inverter":"Тип інвертора: 1) Deye/Sunsynk  2) Інший/власний [1]: ",
        "schedule":"Увімкнути {name} звіти? [{default}]: ",
        "dryrun":"ПРОБНИЙ ЗАПУСК — файли не створено.",
        "exists":"Налаштування вже існують. Перезапис заборонено. Скористайтеся --check.",
        "complete":"Файли налаштувань створено. Застосунок поки не розгорнуто.",
        "check":"Перевірити API Home Assistant зараз? y/N: ",
        "api_ok":"Авторизація в API Home Assistant успішна.",
        "api_fail":"Не вдалося перевірити API Home Assistant: ",
        "invalid":"Некоректне значення: ",
        "abort":"Налаштування скасовано; файлів не створено.",
    },
}


def prompt(message: str, default: str | None = None) -> str:
    value = input(message).strip()
    return value or (default or "")


def hidden_input(message: str) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return getpass.getpass(message).strip()


def select_language(choice: str) -> str:
    if choice == "2":
        return "uk"
    if choice in ("", "1"):
        return "en"
    raise ValueError("Select 1 or 2")




def yesno(value: str, default: bool = False) -> bool:
    value = value.strip().lower()
    if not value:
        return default
    if value in ('y','yes','т','так'):
        return True
    if value in ('n','no','н','ні'):
        return False
    raise ValueError('Expected yes/no (y/n)')


def schedule_yaml(timezone: str, enabled: dict[str,bool]) -> str:
    # This is intentionally compatible with the current fixed-calendar scheduler.
    lines = ['timezone: '+timezone, 'scheduler:', '  check_interval_seconds: 60',
             '  statistics_delay_minutes: 10', '  retry_interval_minutes: 15',
             '  max_attempts: 5', '  catch_up: true', '  catch_up_days: 7', 'reports:']
    schedules = {'daily':('0 0 * * *','previous_day'),
                 'weekly':('0 0 * * 1','previous_week'),
                 'monthly':('0 0 1 * *','previous_month'),
                 'quarterly':('0 0 1 1,4,7,10 *','previous_quarter'),
                 'yearly':('0 0 1 1 *','previous_year')}
    for typ,(cron,period) in schedules.items():
        lines += [f'  {typ}:',f"    enabled: {str(enabled[typ]).lower()}",
                  f'    cron: "{cron}"',f'    period: {period}']
    return '\n'.join(lines)+'\n'

def validate_email(value: str) -> str:
    if not re.fullmatch(r"[^\s@,]+@[^\s@,]+\.[^\s@,]+", value):
        raise ValueError("Expected a single email address")
    return value


def validate_hostname(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", value):
        raise ValueError("Expected a DNS hostname")
    return value


def validate_relative_sensor_path(value: str) -> Path:
    p = Path(value)
    if p.is_absolute() or '..' in p.parts or not str(p).startswith('config/') or p.suffix not in ('.yaml','.yml'):
        raise ValueError("Sensor mapping must be a YAML file under config/")
    resolved = (ROOT / p).resolve()
    if not resolved.is_relative_to((ROOT / 'config').resolve()):
        raise ValueError("Sensor path escapes config directory")
    return resolved


def validate_tz(value: str) -> str:
    try: ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc: raise ValueError("Unknown timezone") from exc
    return value


def check_api(url: str, token: str) -> None:
    with rest_open(url, "/api/", token, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        obj = json.load(response)
        if not isinstance(obj,dict) or 'message' not in obj:
            raise RuntimeError("Unexpected API reply")


def create_exclusive(path: Path, content: str | bytes, mode: int = 0o600) -> None:
    """Create a new private file without overwriting anything or following links."""
    data = content.encode('utf-8') if isinstance(content,str) else content
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os,'O_NOFOLLOW',0),mode)
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def main() -> int:
    try:
        return _main()
    except (KeyboardInterrupt, EOFError):
        print(I18N['en']['abort'], file=sys.stderr)
        return 130
    except Exception:
        print(
            I18N['en']['invalid'] + "[INSTALLATION_ERROR]",
            file=sys.stderr
        )
        return 2


def _main() -> int:
    ap = argparse.ArgumentParser(description="Generate a private Solar Energy Analytics configuration")
    ap.add_argument('--sensor-preview',action='store_true',help='Discover and select sensors without writing files')
    ap.add_argument('--dry-run',action='store_true',help='Prompt but do not write files')
    ap.add_argument('--check',action='store_true',help='Validate existing configuration, no secrets displayed')
    args=ap.parse_args()
    if args.check:
        required=[ROOT/'.env',ROOT/'secrets/ha_token',ROOT/'config/sensors.yaml',ROOT/'config/schedule.yaml']
        for p in required: print(('OK  ' if p.exists() else 'MISS'),p.relative_to(ROOT))
        return 0 if all(p.exists() for p in required) else 1
    lang=select_language(prompt(I18N['en']['language']))
    t=I18N[lang]
    print('\n'+t['title']+'\n'+t['welcome']+'\n')
    existing=[p for p in (ROOT/'.env',ROOT/'secrets/ha_token',ROOT/'secrets/smtp_password',ROOT/'config/sensors.yaml',ROOT/'config/schedule.yaml') if p.exists()]
    if existing and not (args.dry_run or args.sensor_preview):
        print(t['exists'])
        return 2
    try:
        from sensor_wizard import discover, configure
        import yaml
        default_url = 'http://127.0.0.1:8123'
        try:
            rest_open(default_url, '/api/', timeout=2).close()
        except urllib.error.HTTPError as exc:
            if exc.code != 401: default_url = None
        except OSError: default_url = None
        while True:
            try:
                ha_url=validate_url(prompt(('Адреса Home Assistant' if lang=='uk' else 'Home Assistant URL')+(f' [{default_url}]' if default_url else '')+': ',default_url))
                token=hidden_input(t['ha_token'])
                if not token: raise ValueError('Empty token')
                check_api(ha_url, token)
                states, metadata = discover(ha_url, token)
                break
            except (OSError, ValueError, RuntimeError) as exc:
                print(t['api_fail']+type(exc).__name__)
                if prompt('1) Retry / Повторити  0) Cancel / Скасувати [1]: ','1') != '1': return 2
        print(t['api_ok'])
        existing_path=ROOT/'config/sensors.yaml'
        previous=yaml.safe_load(existing_path.read_text()) if existing_path.exists() else None
        mapping = yaml.safe_dump(configure(states, metadata, lang, existing=previous), allow_unicode=True, sort_keys=False)
        print(mapping)
        if args.sensor_preview:
            print(t['dryrun'])
            return 0
        if not yesno(prompt('Confirm mappings? / Підтвердити прив’язки? y/N: ')):
            return 2
        tz=validate_tz(prompt(t['timezone'],'Europe/Kyiv'))
        report_lang=select_language(prompt(t['report_language'], '2' if lang=='uk' else '1'))
        inverter_profile='deye'
        schedule_enabled={}
        names={'daily':('Daily','Щоденні'),'weekly':('Weekly','Щотижневі'),
               'monthly':('Monthly','Щомісячні'),'quarterly':('Quarterly','Щоквартальні'),
               'yearly':('Yearly','Річні')}
        for typ, (en,uk) in names.items():
            default=typ!='quarterly'
            title=(uk if lang=='uk' else en)
            schedule_enabled[typ]=yesno(prompt(t['schedule'].format(name=title,default='Y/n' if default else 'y/N')),default)
        smtp_enabled=yesno(prompt(t['email']))
        smtp={}
        if smtp_enabled:
            smtp['host']=validate_hostname(prompt(t['host']))
            smtp['port']=int(prompt(t['port'],'587'))
            if not 1 <= smtp['port'] <= 65535: raise ValueError('SMTP port out of range')
            smtp['username']=prompt(t['username'])
            if not smtp['username']:raise ValueError('SMTP username required')
            smtp['sender']=validate_email(prompt(t['sender'],smtp['username']))
            smtp['recipient']=validate_email(prompt(t['recipient']))
            smtp['password']=hidden_input(t['password'])
            if not smtp['password']:raise ValueError('SMTP password required')
        sensor_path=ROOT/'config/sensors.yaml'
        if args.dry_run:
            print(t['dryrun'])
            return 0
        # Create only after all validation and prompts. Never display secrets.
        secret_dir=ROOT/'secrets'
        secret_dir.mkdir(mode=0o700,exist_ok=True)
        os.chmod(secret_dir,0o700)
        for directory in ('reports','logs','state'):(ROOT/directory).mkdir(mode=0o700,exist_ok=True)
        env=(f'TZ={tz}\nHA_URL={ha_url}\nHA_TOKEN_FILE=/run/secrets/ha_token\n'
             f'REPORT_TIMEZONE={tz}\nREPORT_LANGUAGE={report_lang}\n'
             f'INVERTER_PROFILE={inverter_profile}\n'
             'REPORT_DIRECTORY=/app/reports\n'
             f'SMTP_ENABLED={str(smtp_enabled).lower()}\n'
             f'SMTP_HOST={smtp.get("host", "")}\nSMTP_PORT={smtp.get("port",587)}\n'
             'SMTP_STARTTLS=true\n'
             f'SMTP_USERNAME={smtp.get("username", "")}\n'
             f'SMTP_FROM={smtp.get("sender", "")}\nSMTP_TO={smtp.get("recipient", "")}\n'
             'SMTP_PASSWORD_FILE=/run/secrets/smtp_password\n'
             f'APP_UID={os.getuid()}\nAPP_GID={os.getgid()}\n')
        written=[]
        try:
            for p, value, mode in ((ROOT/'.env',env,0o600),(secret_dir/'ha_token',token+'\n',0o600),
                                   (secret_dir/'smtp_password',(smtp.get('password') or '')+'\n',0o600),
                                   (sensor_path,mapping,0o600),
                                   (ROOT/'config/schedule.yaml',schedule_yaml(tz,schedule_enabled),0o600)):
                create_exclusive(p,value,mode)
                written.append(p)
        except BaseException:
            for p in written:p.unlink(missing_ok=True)
            raise
        print(t['complete'])

        return 0
    except (KeyboardInterrupt, EOFError):
        print('\n'+t['abort'], file=sys.stderr)
        return 130
    except Exception:
        print(t['invalid']+"[INSTALLATION_ERROR]", file=sys.stderr)
        return 2

if __name__=='__main__':
    sys.exit(main())
