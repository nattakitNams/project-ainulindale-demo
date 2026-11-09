# ทดสอบทุกฟังก์ชันหลักผ่าน API ของตัวประมวลผลจริง (workspace ทดสอบ 41299)
import io
import sys
import time
import traceback

import requests
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, ENGINE, NTL, VECTORS, need, session, wait_engine  # noqa: E402


B = ENGINE
wait_engine()
SP = None
NTL_REAL = str(need(NTL, 'AINU_TEST_NTL'))
s = session
RES = []


def api(path, body=None, method=None, raw=False, ok=True):
    r = s.request(method or ('POST' if body is not None else 'GET'), B + path, json=body, timeout=600)
    if raw:
        if not r.ok:
            raise AssertionError(f'{path} → HTTP {r.status_code} {r.text[:200]}')
        return r
    j = r.json()
    if ok and not r.ok:
        raise AssertionError(f'{path} → {j.get("error")}')
    return j


def check(name, fn):
    t = time.time()
    try:
        out = fn()
        RES.append((True, name, out))
        print(f'✔ {name} ({time.time() - t:.1f}s) {out or ""}')
    except Exception as e:
        RES.append((False, name, str(e)))
        print(f'✘ {name}: {e}')
        traceback.print_exc(limit=1)


def add(path):
    r = api('/api/datasets', dict(paths=[path]))
    if r['added']:
        return r['added'][0]
    nm = path.rsplit('\\', 1)[-1].rsplit('.', 1)[0]
    return [d for d in api('/api/datasets') if d['name'] == nm][-1]['id']


def wait_ready(i, sec=180):
    for _ in range(sec):
        d = api(f'/api/datasets/{i}')
        if (d.get('stats') or {}).get('sample_n'):
            return d
        time.sleep(1)
    raise AssertionError('งานเตรียมข้อมูลไม่เสร็จ')


def wait_job(jid, sec=900):
    for _ in range(sec):
        j = api(f'/api/jobs/{jid}')
        j = j.get('job', j)
        if j['status'] in ('done', 'failed', 'cancelled'):
            if j['status'] != 'done':
                raise AssertionError(f'งาน {j["status"]}: {j.get("error")}')
            return j
        time.sleep(1)
    raise AssertionError('งานไม่เสร็จในเวลา')


ID = {}
check('hello / state / system', lambda: (api('/api/engine/hello')['mode'], len(api('/api/state')), api('/api/system').get('version')))


def _add_all():
    for k, p in [('wp', str(need(DATA, 'AINU_TEST_DATA') / 'wp_bkk.tif')), ('ndvi', str(DATA / 'ndvi_bkk.tif')), ('ntl', NTL_REAL)]:
        ID[k] = add(p)
    for k in ID:
        wait_ready(ID[k])
    return {k: api(f'/api/datasets/{i}')['value_type'] for k, i in ID.items()}


check('เพิ่มไฟล์ + เตรียมข้อมูล (WorldPop, NDVI, night light จริง)', _add_all)
check('ยืนยันประเภทค่า', lambda: [api(f'/api/datasets/{ID[k]}', dict(value_type=v, value_type_confirmed=True), 'PATCH') and v
                                for k, v in (('wp', 'count'), ('ndvi', 'density'), ('ntl', 'density'))])


def _styles():
    out = {}
    for k in ID:
        st = api(f'/api/datasets/{ID[k]}/style')['style']
        out[k] = f"{st['type']} {st.get('ramp', '')} {round(st.get('min') or 0, 3)}…{round(st.get('max') or 0, 3)}"
    ntl = api(f'/api/datasets/{ID["ntl"]}/style')['style']
    assert ntl['type'] == 'gray' and ntl['max'] > 5, f'night light stretch ผิด: {ntl}'
    return out


check('สไตล์เริ่มต้น (QGIS-like)', _styles)


def _classify():
    out = {}
    for k in ID:
        for t in ('pseudocolor', 'gray'):
            r = api(f'/api/datasets/{ID[k]}/classify', dict(type=t, ramp='viridis', mode='continuous', interp='linear', classes=5, metric='value'))['style']
            out[f'{k}:{t}'] = f"{round(r.get('min'), 2)}…{round(r.get('max'), 2)}"
        for mode in ('equal', 'quantile'):
            api(f'/api/datasets/{ID[k]}/classify', dict(type='pseudocolor', ramp='YlOrRd', mode=mode, interp='discrete', classes=5, metric='value'))
    r = api(f'/api/datasets/{ID["ntl"]}/classify', dict(type='paletted', ramp='viridis'))['style']
    out['ntl:paletted'] = f"{len(r['entries'])} ค่า"
    e = api(f'/api/datasets/{ID["ndvi"]}/classify', dict(type='paletted', ramp='viridis'), ok=False)
    out['ndvi:paletted'] = 'ปฏิเสธ (ทศนิยม) ✔' if e.get('error') else f"{len(e['style']['entries'])} ค่า"
    return out


check('Classify ทุกแบบ (pseudocolor/gray/paletted, equal/quantile)', _classify)


def _style_roundtrip():
    i = ID['ntl']
    st = api(f'/api/datasets/{i}/classify', dict(type='pseudocolor', ramp='magma', mode='continuous', interp='linear', classes=5, metric='value'))['style']
    api(f'/api/datasets/{i}/style', dict(style=st))
    assert api(f'/api/datasets/{i}/style')['saved']
    q = api(f'/api/datasets/{i}/style.qml', raw=True).text
    assert 'singlebandpseudocolor' in q
    tok = api('/api/style-preview', dict(dataset_id=i, style=st))['token']
    png = api(f'/api/datasets/{i}/tile/6/50/29.png?st={tok}', raw=True).content
    api(f'/api/datasets/{i}/style', dict(style=None))
    assert not api(f'/api/datasets/{i}/style')['saved']
    return f'qml {len(q)}B · tile {len(png)}B'


check('บันทึก/คืนค่าสไตล์ + .qml + style-preview', _style_roundtrip)


def _tiles():
    out = {}
    for k in ID:
        n = 0
        for z, x, y in ((2, 3, 1), (6, 50, 29), (9, 404, 236), (12, 3232, 1890)):
            r = api(f'/api/datasets/{ID[k]}/tile/{z}/{x}/{y}.png', raw=True)
            assert r.headers['Content-Type'].startswith('image/png')
            n += 1
        out[k] = n
    return out


check('ไทล์แผนที่ (z2–z12)', _tiles)
check('อ่านค่าจุด (กทม. + ลองจิจูดวนรอบ)', lambda: (api(f'/api/datasets/{ID["ntl"]}/point?lon=100.5018&lat=13.7563&z=10'),
                                                api(f'/api/datasets/{ID["wp"]}/point?lon=100.5018&lat=13.7563&z=10').get('value')))
check('ตัวเลือกความละเอียด WorldPop × night light จริง', lambda: [o['label'] for o in api(f'/api/res-options?ids={ID["wp"]},{ID["ntl"]}')['options']])
check('พรีวิวควอนไทล์', lambda: {k: api('/api/classes-preview', dict(dataset_id=ID[k], cfg=dict(n=3, method='quantile', metric='value' if k != 'wp' else 'density'))).get('breaks') for k in ID})


def _aoi():
    txt = '100.45 13.70\n100.60 13.70\n100.60 13.82\n100.45 13.82'
    p = api('/api/aoi/parse-coords', dict(text=txt))
    a = api('/api/aoi', dict(name='ทดสอบ smoke', coords=txt))
    aid = a.get('id') or a.get('aoi', {}).get('id')
    gj = api(f'/api/aoi/{aid}.geojson', raw=True).json()
    ID['aoi'] = aid
    return f"{p['area_km2']} km² · id {aid} · {gj.get('type')}"


check('พื้นที่ศึกษา: พิมพ์พิกัด → บันทึก → geojson', _aoi)


def _biv(aoi):
    opts = api(f'/api/res-options?ids={ID["wp"]},{ID["ntl"]}')['options']
    res = opts[0]['value'] if 'value' in opts[0] else opts[0]['res']
    job = dict(name='smoke ntl×pop' + (' aoi' if aoi else ''), target_res=str(res),
               x=dict(dataset_id=ID['wp'], n=3, method='quantile', metric='density', label='ประชากร'),
               y=dict(dataset_id=ID['ntl'], n=3, method='quantile', metric='value', label='แสงไฟ'),
               colors=['#e8e8e8', '#e4acac', '#c85a5a', '#b0d5df', '#ad9ea5', '#985356', '#64acbe', '#627f8c', '#574249'], highlight=[9])
    if aoi:
        job['aoi_id'] = ID['aoi']
    est = api('/api/estimate', dict(kind='bivariate', params=job))
    assert est.get('ok'), est.get('error')
    j = wait_job(api('/api/jobs', dict(kind='bivariate', params=job))['job'])
    sm = j['result']['summary']
    ID['map'] = j['result'].get('dataset_id') or ID.get('map')
    return f"res {res} · {est['grid']['width']}×{est['grid']['height']} · คนรวม {sm['weight_total']:,.0f} · warn {j['result'].get('warnings')}"


check('ไบแวเรียต night light จริง × WorldPop', lambda: _biv(False))
check('ไบแวเรียต + พื้นที่ศึกษา', lambda: _biv(True))


def _resample():
    bad = api('/api/estimate', dict(kind='resample', params=dict(dataset_id=ID['ntl'], target_res='0.01', aoi_id=ID['aoi'])))
    assert not bad.get('ok') and 'เกินหน่วยความจำ' in bad.get('error', ''), f'ไม่ได้กันงานยักษ์: {bad}'
    out = []
    for res in ('30', '3'):
        j = dict(dataset_id=ID['ntl'], target_res=res, aoi_id=ID['aoi'])
        est = api('/api/estimate', dict(kind='resample', params=j))
        assert est.get('ok'), est.get('error')
        r = wait_job(api('/api/jobs', dict(kind='resample', params=j))['job'])
        out.append(f"{res}″ {est['grid']['width']}×{est['grid']['height']} sum {r['result']['summary']['sum']:,.0f}")
    return 'กัน 0.01″ ✔ · ' + ' · '.join(out)


check('ปรับความละเอียด night light + ตัดพื้นที่', _resample)


def _maps():
    ds = api('/api/datasets')
    maps = [d for d in ds if d.get('role') == 'map']
    assert maps, 'ไม่มีแผนที่ผลลัพธ์'
    m = maps[-1]
    st = api(f'/api/datasets/{m["id"]}/style')['style']
    png = api(f'/api/datasets/{m["id"]}/tile/9/404/236.png', raw=True).content
    ID['map'] = m['id']
    return f'{m["name"]} · {st["type"]} {len(st.get("entries", []))} สี · tile {len(png)}B'


check('แผนที่ผลลัพธ์ในคลัง + ไทล์', _maps)


def _report():
    spec = dict(basemap='esri_light', boundary=None, layers=[dict(key=f'ds:{ID["map"]}', opacity=1), dict(key=f'ds:{ID["ntl"]}', opacity=1)])
    v = api('/api/report/view', dict(map=spec, w=180, h=120))['view']
    m = api('/api/report/map', dict(map=spec, w=180, h=120, dpi=90, view=v))
    inf = api('/api/report/info', dict(map=spec))
    ins = api('/api/report/inset', dict(ext=v.get('ext') or [100.3, 13.5, 100.9, 14.0], w=40, h=40, dpi=90))
    img = api(f'/api/report/img/{m["key"]}.png', raw=True).content if 'key' in m else b''
    return f'map {list(m)[:4]} · info {list(inf)[:4]} · inset {list(ins)[:3]} · img {len(img)}B'


check('รายงาน: view/map/info/inset', _report)
check('ข้อมูลพื้นฐาน GISTDA', lambda: [d['name'] for d in api('/api/datasets') if d.get('meta', {}).get('builtin')] or api('/api/basedata'))


def _links():
    bd = [d for d in api('/api/datasets') if d.get('kind') == 'link' and 'Province' in d['name']]
    if not bd:
        return 'ไม่มีลิงก์จังหวัด (ออฟไลน์?)'
    i = bd[0]['id']
    f = api(f'/api/links/{i}/features?bbox=100.3,13.5,100.9,14.0&z=9')
    return f"features {len(f.get('features') or f.get('geojson', {}).get('features', []))}"


check('ลิงก์ GISTDA: ดึงฟีเจอร์', _links)
check('งาน / จานสี / workspace', lambda: (len(api('/api/jobs')), len(api('/api/palettes') if isinstance(api('/api/palettes'), list) else api('/api/palettes').get('palettes', []))))
check('ลบพื้นที่ศึกษาทดสอบ', lambda: api(f'/api/aoi/{ID["aoi"]}', method='DELETE') and 'ok')

bad = [r for r in RES if not r[0]]
print(f'\nผล: ผ่าน {len(RES) - len(bad)}/{len(RES)}')
for r in bad:
    print('   ✘', r[1], '—', r[2][:300])
