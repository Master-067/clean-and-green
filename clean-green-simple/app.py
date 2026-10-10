from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO
import sqlite3, random, math
from datetime import datetime

app=Flask(__name__); app.secret_key='clean-green-demo-secret'; socketio=SocketIO(app,cors_allowed_origins='*'); DB='clean_green.db'
def now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def conn():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def status(x): return 'Overflow Risk' if x>=80 else ('Attention' if x>=60 else 'Normal')
def init():
    c=conn(); c.executescript('''
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT,email TEXT UNIQUE,password TEXT,role TEXT,green_points INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS workers(id INTEGER PRIMARY KEY,user_id INTEGER UNIQUE,digital_id TEXT UNIQUE,insurance_status TEXT,safety_score INTEGER,verified INTEGER,upi_id TEXT);
CREATE TABLE IF NOT EXISTS bins(id INTEGER PRIMARY KEY,code TEXT UNIQUE,type TEXT,fill_level INTEGER,latitude REAL,longitude REAL,status TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS vehicles(id INTEGER PRIMARY KEY,vehicle_no TEXT UNIQUE,status TEXT,latitude REAL,longitude REAL,worker_id INTEGER);
CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY,citizen_id INTEGER,bin_id INTEGER,category TEXT,description TEXT,priority TEXT,status TEXT,created_at TEXT);
CREATE TABLE IF NOT EXISTS pickups(id INTEGER PRIMARY KEY,citizen_id INTEGER,worker_id INTEGER,address TEXT,waste_type TEXT,scheduled_for TEXT,estimated_kg REAL,status TEXT,created_at TEXT,completed_at TEXT);
CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY,worker_id INTEGER,pickup_id INTEGER,amount REAL,method TEXT,status TEXT);
''')
    users=[('Demo Citizen','citizen@example.com','password123','citizen',120),('Demo Worker','worker@example.com','password123','worker',0),('ULB Admin','admin@example.com','password123','admin',0)]
    for u in users:c.execute('INSERT OR IGNORE INTO users(name,email,password,role,green_points) VALUES(?,?,?,?,?)',u)
    w=c.execute("SELECT id FROM users WHERE email='worker@example.com'").fetchone(); c.execute("INSERT OR IGNORE INTO workers(user_id,digital_id,insurance_status,safety_score,verified,upi_id) VALUES(?,?,?,?,?,?)",(w['id'],'CG-WKR-0001','Active',100,1,'worker@upi'))
    for b in [('BIN-001','Wet',82,13.0827,80.2707),('BIN-002','Dry',42,13.0878,80.2785),('BIN-003','Mixed',67,13.075,80.265),('BIN-004','Dry',25,13.09,80.285),('BIN-005','Wet',91,13.072,80.258)]: c.execute('INSERT OR IGNORE INTO bins(code,type,fill_level,latitude,longitude,status,updated_at) VALUES(?,?,?,?,?,?,?)',(*b,status(b[2]),now()))
    c.execute("INSERT OR IGNORE INTO vehicles(vehicle_no,status,latitude,longitude,worker_id) VALUES(?,?,?,?,?)",('TN-01-CG-1001','On Route',13.08,80.275,w['id']))
    c.commit(); c.close()
def user():
    if 'user_id' not in session:return None
    c=conn(); x=c.execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone(); c.close(); return dict(x) if x else None
def require(role=None):
    u=user()
    if not u:return None, (jsonify(error='Login required'),401)
    if role and u['role']!=role:return None,(jsonify(error='Access denied'),403)
    return u,None

@app.route('/')
def home():return render_template('index.html')
@app.post('/api/login')
def login():
    d=request.json;c=conn();u=c.execute('SELECT * FROM users WHERE email=? AND password=?',(d.get('email'),d.get('password'))).fetchone();c.close()
    if not u:return jsonify(error='Invalid credentials'),401
    session['user_id']=u['id'];return jsonify(dict(u))
@app.post('/api/logout')
def logout():session.clear();return jsonify(ok=True)
@app.get('/api/bins')
def bins():
    c=conn();x=c.execute('SELECT * FROM bins ORDER BY fill_level DESC').fetchall();c.close();return jsonify([dict(r) for r in x])
@app.get('/api/vehicles')
def vehicles():
    c=conn();x=c.execute('SELECT * FROM vehicles').fetchall();c.close();return jsonify([dict(r) for r in x])
@app.get('/api/admin/summary')
def summary():
    u,e=require('admin');
    if e:return e
    c=conn();x={'open_reports':c.execute("SELECT count(*) FROM reports WHERE status!='Resolved'").fetchone()[0],'active_pickups':c.execute("SELECT count(*) FROM pickups WHERE status!='Completed'").fetchone()[0],'overflow_bins':c.execute('SELECT count(*) FROM bins WHERE fill_level>=80').fetchone()[0],'workers':c.execute('SELECT count(*) FROM workers WHERE verified=1').fetchone()[0]};c.close();return jsonify(x)
@app.get('/api/reports')
def get_reports():
    u,e=require();
    if e:return e
    c=conn();q='SELECT reports.*,bins.code FROM reports LEFT JOIN bins ON bins.id=reports.bin_id';args=()
    if u['role']=='citizen':q+=' WHERE citizen_id=?';args=(u['id'],)
    x=c.execute(q+' ORDER BY reports.id DESC',args).fetchall();c.close();return jsonify([dict(r) for r in x])
@app.post('/api/reports')
def report():
    u,e=require('citizen');
    if e:return e
    d=request.json;c=conn();cur=c.execute('INSERT INTO reports(citizen_id,bin_id,category,description,priority,status,created_at) VALUES(?,?,?,?,?,?,?)',(u['id'],d.get('bin_id') or None,d.get('category','Overflow'),d.get('description',''),'High' if d.get('category')=='Overflow' else 'Medium','Open',now()));c.commit();x=c.execute('SELECT * FROM reports WHERE id=?',(cur.lastrowid,)).fetchone();c.close();socketio.emit('report_created',dict(x));return jsonify(dict(x)),201
@app.post('/api/reports/<int:i>/resolve')
def resolve(i):
    u,e=require();
    if e:return e
    if u['role'] not in ('admin','worker'):return jsonify(error='Access denied'),403
    c=conn();c.execute("UPDATE reports SET status='Resolved' WHERE id=?",(i,));c.commit();x=c.execute('SELECT * FROM reports WHERE id=?',(i,)).fetchone();c.close();socketio.emit('report_updated',dict(x));return jsonify(dict(x))
@app.get('/api/pickups')
def get_pickups():
    u,e=require();
    if e:return e
    c=conn();q='SELECT * FROM pickups';args=()
    if u['role']=='citizen':q+=' WHERE citizen_id=?';args=(u['id'],)
    elif u['role']=='worker':
        w=c.execute('SELECT id FROM workers WHERE user_id=?',(u['id'],)).fetchone();q+=' WHERE worker_id=?';args=(w['id'] if w else -1,)
    x=c.execute(q+' ORDER BY id DESC',args).fetchall();c.close();return jsonify([dict(r) for r in x])
@app.post('/api/pickups')
def pickup():
    u,e=require('citizen');
    if e:return e
    d=request.json;c=conn();w=c.execute('SELECT id FROM workers WHERE verified=1 LIMIT 1').fetchone();cur=c.execute('INSERT INTO pickups(citizen_id,worker_id,address,waste_type,scheduled_for,estimated_kg,status,created_at) VALUES(?,?,?,?,?,?,?,?)',(u['id'],w['id'] if w else None,d['address'],d['waste_type'],d['scheduled_for'],float(d.get('estimated_kg',1)),'Assigned' if w else 'Requested',now()));c.commit();x=c.execute('SELECT * FROM pickups WHERE id=?',(cur.lastrowid,)).fetchone();c.close();socketio.emit('pickup_created',dict(x));return jsonify(dict(x)),201
@app.post('/api/pickups/<int:i>/status')
def pickup_status(i):
    u,e=require();
    if e:return e
    if u['role'] not in ('worker','admin'):return jsonify(error='Access denied'),403
    s=request.json.get('status');c=conn();p=c.execute('SELECT * FROM pickups WHERE id=?',(i,)).fetchone()
    if not p:c.close();return jsonify(error='Not found'),404
    c.execute('UPDATE pickups SET status=?,completed_at=? WHERE id=?',(s,now() if s=='Completed' else None,i))
    if s=='Completed':
        c.execute('INSERT INTO payments(worker_id,pickup_id,amount,method,status) VALUES(?,?,?,?,?)',(p['worker_id'],i,p['estimated_kg']*20,'UPI','Mocked'));c.execute('UPDATE users SET green_points=green_points+20 WHERE id=?',(p['citizen_id'],))
    c.commit();x=c.execute('SELECT * FROM pickups WHERE id=?',(i,)).fetchone();c.close();socketio.emit('pickup_updated',dict(x));return jsonify(dict(x))
@app.get('/api/worker')
def get_worker():
    u,e=require('worker');
    if e:return e
    c=conn();x=c.execute('SELECT workers.*,users.name,users.email FROM workers JOIN users ON users.id=workers.user_id WHERE workers.user_id=?',(u['id'],)).fetchone();c.close();return jsonify(dict(x))
@app.post('/api/worker/safety')
def safety():
    u,e=require('worker');
    if e:return e
    d=request.json;score=100 if all(d.get(x) for x in ['gloves','mask','shoes','vest']) else 80;c=conn();c.execute('UPDATE workers SET safety_score=? WHERE user_id=?',(score,u['id']));c.commit();c.close();return jsonify(safety_score=score)
@app.post('/api/simulate')
def simulate():
    u,e=require('admin');
    if e:return e
    c=conn()
    for b in c.execute('SELECT * FROM bins').fetchall():
        n=max(5,min(100,b['fill_level']+random.randint(-8,12)));c.execute('UPDATE bins SET fill_level=?,status=?,updated_at=? WHERE id=?',(n,status(n),now(),b['id']))
    v=c.execute('SELECT * FROM vehicles LIMIT 1').fetchone();a=random.random()*math.pi*2
    if v:c.execute('UPDATE vehicles SET latitude=?,longitude=?,status="On Route" WHERE id=?',(v['latitude']+math.sin(a)*.002,v['longitude']+math.cos(a)*.002,v['id']))
    c.commit();bs=[dict(x) for x in c.execute('SELECT * FROM bins')];vs=[dict(x) for x in c.execute('SELECT * FROM vehicles')];c.close();socketio.emit('live_update',{'bins':bs,'vehicles':vs});return jsonify(ok=True)

if __name__=='__main__':
    init();print('Clean & Green: http://127.0.0.1:5000');socketio.run(app,host='127.0.0.1',port=5000,debug=True)
