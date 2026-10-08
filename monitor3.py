#!/usr/bin/env python3
"""GFW gridded apparent fishing effort, NOT confirmed sardine locations."""
import os, json, datetime as dt, urllib.request, urllib.parse, urllib.error, html, pathlib, sys
TOKEN=os.environ.get('GFW_API_TOKEN','').strip()
OUT=pathlib.Path('site'); OUT.mkdir(exist_ok=True)
NOW=dt.datetime.now(dt.timezone.utc)
# Data GFW fishing-effort typically lag 96 hours. End boundary exclusive.
END=(NOW-dt.timedelta(days=4)).date()
START=END-dt.timedelta(days=7)
# Study region; indicative bounding area only, not coordinates of Lizbeth installation.
BBOX=(12.10,44.65,13.75,45.60) # west,south,east,north
WEST,SOUTH,EAST,NORTH=BBOX
GEOMETRY={"type":"Polygon","coordinates":[[[WEST,SOUTH],[EAST,SOUTH],[EAST,NORTH],[WEST,NORTH],[WEST,SOUTH]]]}
BASE='https://gateway.api.globalfishingwatch.org/v3/4wings/report'
# Select purse seine and seine activity. Do not assert target species. Falls back to unfiltered data only on API query errors.
GEARS=['purse_seines','other_purse_seines','seiners','other_seines']

def request_effort(filtered=True):
    params={'spatial-resolution':'LOW','temporal-resolution':'ENTIRE','spatial-aggregation':'false',
      'datasets[0]':'public-global-fishing-effort:latest','date-range':f'{START},{END}', 'format':'JSON', 'group-by':'GEARTYPE'}
    # Group by gear; classification happens locally, avoiding unsupported filter names.
    url=BASE+'?'+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,data=json.dumps({'geojson':GEOMETRY}).encode(),method='POST',headers={
      'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=120) as r:
        import zipfile, io
        raw=r.read()
        if raw[:2] == b'PK':
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                candidates=[n for n in z.namelist() if n.endswith('.json')]
                if not candidates: raise ValueError('Archive API privo di JSON')
                return json.loads(z.read(candidates[0]))
        return json.loads(raw)

def unpack(data):
    rows=[]
    def walk(obj):
        if isinstance(obj,list):
            for i in obj:walk(i)
        elif isinstance(obj,dict):
            if all(k in obj for k in ('lat','lon','hours')) and str(obj.get('geartype','')).lower() in GEARS:
                try:
                    lat,lon,hrs=float(obj['lat']),float(obj['lon']),float(obj['hours'])
                    if SOUTH<=lat<=NORTH and WEST<=lon<=EAST and hrs>0:
                        rows.append({'lat':lat,'lon':lon,'hours':round(hrs,3)})
                except (TypeError,ValueError): pass
            else:
                for v in obj.values():walk(v)
    walk(data.get('entries',[]) if isinstance(data,dict) else data)
    merged={}
    for r in rows:
        key=(r['lat'],r['lon']); merged[key]=merged.get(key,0)+r['hours']
    return [{'lat':k[0],'lon':k[1],'hours':round(v,3)} for k,v in sorted(merged.items(),key=lambda x:-x[1])]

def render(points,status,filter_status):
    # Strictly no fictitious hotspots on errors or empty response.
    payload=json.dumps(points,ensure_ascii=False)
    generated=NOW.strftime('%d/%m/%Y %H:%M UTC')
    content=f'''<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Adriatico – attività di pesca osservata</title><link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>body{{font-family:system-ui,Arial;margin:0;background:#f3f7f9;color:#123}}header{{padding:14px 16px;background:#092f47;color:#fff}}h1{{font-size:20px;margin:0 0 5px}}header p{{margin:0}}.note{{margin:10px 14px;padding:12px;background:#fff;border-radius:9px;line-height:1.5}}#map{{height:65vh;min-height:370px}}.small{{font-size:13px;color:#4b5965}}</style></head>
<body><header><h1>Adriatico: attività apparente di pesca</h1><p>Chioggia · Rosolina · mare aperto</p></header>
<div class="note"><b>Ultimo tentativo:</b> {html.escape(generated)}<br><b>Periodo dati:</b> {START} – {END} (fine esclusa; ritardo previsto ≥ 4 giorni)<br>
<b>Risultato:</b> {html.escape(status)}<br><b>Filtro:</b> {html.escape(filter_status)}</div><div id="map"></div>
<div class="note small"><b>Importante:</b> queste celle indicano soltanto ore di <i>attività di pesca apparente</i> associate ad attrezzi classificati. Non mostrano tracce AIS in tempo reale, catture di sardine o presenza di tonni. Una zona senza celle non significa assenza di pesce. La copertura dei dati AIS è incompleta. Coordinate riferite a celle aggregate, non punti esatti della pesca. Fonte: Global Fishing Watch, API 4Wings – public-global-fishing-effort:latest. Uso personale non commerciale.</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
let m=L.map('map').setView([45.10,12.92],9);L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{attribution:'&copy; OpenStreetMap contributors'}}).addTo(m);
let data={payload};let vals=data.map(x=>x.hours),max=Math.max(1,...vals);for(let p of data){{let t=Math.min(1,p.hours/max);let col=t>.65?'#cb3030':t>.25?'#e6a123':'#268f83';L.circleMarker([p.lat,p.lon],{{radius:6+11*Math.sqrt(t),color:'#25394b',weight:1,fillColor:col,fillOpacity:.7}}).addTo(m).bindPopup('<b>Attività apparente</b><br>'+p.hours+' ore aggregate<br>Cella: '+p.lat.toFixed(3)+', '+p.lon.toFixed(3)+'<br>Non è una conferma di sardine');}}
L.rectangle([[{SOUTH},{WEST}],[{NORTH},{EAST}]],{{color:'#124e79',weight:1,fill:false,dashArray:'5,5'}}).addTo(m);
</script></body></html>'''
    (OUT/'index.html').write_text(content,encoding='utf8')
    (OUT/'data.json').write_text(json.dumps({'generated_utc':NOW.isoformat(),'date_start':str(START),'date_end_exclusive':str(END),'status':status,'filter':filter_status,'cells':points},indent=2),encoding='utf8')

if __name__=='__main__':
    if not TOKEN:
        render([],'Errore: secret GFW_API_TOKEN mancante','Non eseguito');print('ERROR: missing GFW_API_TOKEN');sys.exit(1)
    try:
        data=request_effort(True)
        points=unpack(data)
        msg=f'{len(points)} celle con attività apparente rilevata' if points else 'Nessuna cella restituita per il filtro selezionato'
        render(points,msg,'Pesca con reti a circuizione / sciabiche (classificazione GFW)')
        print(msg)
    except urllib.error.HTTPError as e:
        # Do not print server response: avoid logging any sensitive detail.
        status=f'Richiesta API non riuscita: HTTP {e.code}. Nessuna mappa aggiornata.'
        render([],status,'Nessun dato verificato')
        print(status)
        # Show only a short, sanitized error description; never print secrets or URLs.
        try:
            detail=json.loads(e.read(4096).decode('utf8','replace'))
            message='; '.join(str(x.get('title','')) + ': ' + str(x.get('detail','')) for x in detail.get('messages',[]) if isinstance(x,dict))
            if not message: message=str(detail.get('error',''))
            message=message.replace(TOKEN,'[REDACTED]')[:500]
            print('Motivo server GFW:',message if message else 'non specificato')
        except Exception: pass
        sys.exit(1)
    except Exception as e:
        render([],'Errore nel recupero dati; nessuna rilevazione verificata','Nessun dato verificato')
        print('ERROR',type(e).__name__);sys.exit(1)
