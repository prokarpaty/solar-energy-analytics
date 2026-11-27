"""Interactive read-only discovery; configuration is saved only by the caller."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ha_connection import rest_open, connect_websocket
from sensor_discovery import candidates
from sensor_validation import ENERGY_ROLES, REQUIRED_ENERGY, validate_configuration, measurement_target


def discover(url, token):
    try:
        return _discover(url, token)
    except Exception:
        raise RuntimeError(
            "HA sensor discovery failed"
        ) from None


def _discover(url, token):
    with rest_open(url, '/api/states', token, timeout=30) as response:
        states = json.load(response)
    ws = connect_websocket(url, timeout=30)
    try:
        if json.loads(ws.recv()).get('type') != 'auth_required': raise RuntimeError('Unexpected WebSocket response')
        ws.send(json.dumps({'type':'auth','access_token':token}))
        if json.loads(ws.recv()).get('type') != 'auth_ok': raise RuntimeError('WebSocket authentication failed')
        ws.send(json.dumps({'id':1,'type':'recorder/list_statistic_ids'}))
        while True:
            reply=json.loads(ws.recv())
            if reply.get('id') == 1: break
        if not reply.get('success'): raise RuntimeError('Historical statistics discovery failed')
        return states, reply['result']
    finally:
        try:
            ws.close()
        except Exception:
            pass


def configure(states, metadata, lang='en', ask=input, show=print, existing=None):
    import re
    import copy
    from sensor_validation import validate
    uk=lang=='uk'
    def tr(en, ua): return ua if uk else en
    registry={m['statistic_id']:m for m in metadata}
    live={s['entity_id']:s for s in states}
    def menu(options, default=None):
        for key,label in options.items(): show(f'[{key}] {label}')
        while True:
            value=ask(tr('Choice','Ваш вибір')+(f' [{default}]' if default else '')+': ').strip() or default
            if value in options: return value
            show(tr('Choose a displayed option.','Оберіть один із зазначених варіантів.'))
    prefixes=sorted({m.group(1) for entity in live if (m:=re.fullmatch(r'(sensor\..+_)total_production',entity)) and entity in registry})
    if not prefixes: raise ValueError(tr('No supported Deye sensor naming profile found.','Не знайдено підтримуваний профіль датчиків Deye.'))
    if len(prefixes)==1: prefix=prefixes[0]
    else:
        choice=menu({**{str(i):p for i,p in enumerate(prefixes,1)},'0':tr('Cancel','Скасувати')})
        if choice=='0': raise KeyboardInterrupt
        prefix=prefixes[int(choice)-1]
    show(tr('Confirm Deye entity prefix: ','Підтвердьте префікс сутностей Deye: ')+prefix)
    if menu({'1':tr('Confirm','Підтвердити'),'0':tr('Cancel','Скасувати')},'1')=='0': raise KeyboardInterrupt
    roles={('energy',k):v for k,v in zip(ENERGY_ROLES,('total_production','total_load_consumption','total_energy_import','total_energy_export','total_battery_charge','total_battery_discharge','total_losses'))}
    roles.update({('power',k):v for k,v in zip(('solar','house','grid','battery','losses'),('pv_power','load_power','grid_power','battery_power','power_losses'))})
    roles[('grid','frequency')]='grid_frequency'
    phases=sorted({int(m.group(1)) for e in live if (m:=re.fullmatch(re.escape(prefix)+r'(?:grid|load)_l([123])_(?:voltage|power)',e))})
    pv=sorted({int(m.group(1)) for e in live if (m:=re.fullmatch(re.escape(prefix)+r'pv(\d+)_power',e))})
    batteries=sorted({int(m.group(1)) for e in live if (m:=re.fullmatch(re.escape(prefix)+r'battery_(\d+)(?:_voltage)?',e))})
    for i in pv: roles[('power',f'pv{i}')]=f'pv{i}_power'
    for i in phases:
        for k in ('voltage','power'):
            roles[('grid',k,f'l{i}')]=f'grid_l{i}_{k}'
            roles[('house','phases',f'l{i}',k)]=f'load_l{i}_{k}'
    for k in ('soc','soh','voltage','current','temperature','capacity'):
        roles[('battery_bank',k)]='battery'+('' if k=='soc' else '_'+k)
    for i in batteries:
        for k in ('soc','soh','voltage','current','temperature','mos_temperature','min_cell_voltage','max_cell_voltage','imbalance'):
            roles[('batteries',f'battery_{i}',k)]=f'battery_{i}'+('' if k=='soc' else '_'+k)
    roles[('temperature','inverter')]='temperature'
    roles[('temperature','inverter_dc')]='dc_temperature'
    def put(config,path,value):
        node=config
        for key in path[:-1]: node=node.setdefault(key,{})
        if value is None: node.pop(path[-1],None)
        else: node[path[-1]]=value
    def get(config,path):
        for key in path:
            if not isinstance(config,dict): return None
            config=config.get(key)
        return config
    def compatible(path,entity):
        if entity != prefix+roles[path] or entity not in live: return False
        try: validate(registry.get(entity),'kWh' if path[0]=='energy' else measurement_target(path),path[0]=='energy')
        except ValueError: return False
        return True
    auto={'energy':{}}
    for path,suffix in roles.items():
        entity=prefix+suffix
        if compatible(path,entity): put(auto,path,entity)
    options={'1':tr('Automatic Deye setup','Автоматичне налаштування Deye'),'3':tr('Advanced: review and edit Deye roles','Розширене: редагувати датчики Deye'),'0':tr('Cancel','Скасувати')}
    if existing is not None: options['2']=tr('Reuse validated existing Deye mappings','Використати наявні перевірені датчики Deye')
    mode=menu(dict(sorted(options.items(),key=lambda x:x[0]=='0' or False)),'1')
    if mode=='0': raise KeyboardInterrupt
    config=copy.deepcopy(auto)
    if mode=='2':
        config={'energy':{}}
        for path in roles:
            entity=get(existing,path)
            if entity and compatible(path,entity): put(config,path,entity)
            elif entity: show(tr('Excluded incompatible mapping: ','Виключено несумісну прив’язку: ')+'.'.join(path))
    def review():
        for i,path in enumerate(roles,1): show(f'{i:02d}. {".".join(path)}: {get(config,path) or tr("not mapped","не зіставлено")}')
    def edit():
        while True:
            review()
            choice=menu({**{str(i):'.'.join(p) for i,p in enumerate(roles,1)},'0':tr('Return to summary','До підсумку')})
            if choice=='0': return
            path=list(roles)[int(choice)-1]; entity=prefix+roles[path]
            opts={'0':tr('Keep current mapping','Залишити поточне')}
            if compatible(path,entity): opts['1']=entity
            if path not in [('energy',r) for r in REQUIRED_ENERGY]: opts['2']=tr('Skip sensor','Пропустити датчик')
            action=menu(opts,'0')
            if action=='1': put(config,path,entity)
            elif action=='2': put(config,path,None)
    if mode=='3': edit()
    while True:
        show(tr('Detected topology (entity names, not hardware verification): ','Виявлена топологія (за назвами сутностей): ')+f'{len(phases)} / {len(pv)} / {len(batteries)} '+tr('phases / PV / batteries','фази / PV / АКБ'))
        show(tr('Mapped roles: ','Зіставлено датчиків: ')+str(sum(bool(get(config,p)) for p in roles)))
        missing=[p for p in roles if not get(config,p)]
        if missing: show(tr('Unmapped: ','Не зіставлено: ')+', '.join('.'.join(p) for p in missing))
        choice=menu({'1':tr('Confirm configuration','Підтвердити конфігурацію'),'2':tr('Review all mappings','Переглянути всі прив’язки'),'3':tr('Edit mappings','Редагувати прив’язки'),'0':tr('Cancel','Скасувати')},'1')
        if choice=='0': raise KeyboardInterrupt
        if choice=='2': review(); continue
        if choice=='3': edit(); continue
        _,_,_,warnings=validate_configuration(config,registry)
        if warnings: raise ValueError('; '.join(warnings))
        return config
