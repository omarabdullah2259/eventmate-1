import os
from functools import wraps
from flask import Flask, render_template, redirect, url_for, session, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from authlib.integrations.flask_client import OAuth
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
secret_key = os.environ.get('FLASK_SECRET_KEY')
if not secret_key:
    raise RuntimeError('FLASK_SECRET_KEY environment variable is required. Do not store secrets in source code.')
app.secret_key = secret_key

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///eventmate.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
db = SQLAlchemy(app)

oauth = OAuth(app)
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')

if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    oauth.register(
        name='google',
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        access_token_url='https://oauth2.googleapis.com/token',
        authorize_url='https://accounts.google.com/o/oauth2/v2/auth',
        api_base_url='https://openidconnect.googleapis.com/v1/',
        client_kwargs={'scope': 'openid email profile', 'prompt': 'select_account'},
    )

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    name = db.Column(db.String(120), nullable=False)
    first_name = db.Column(db.String(60))
    last_name = db.Column(db.String(60))
    state = db.Column(db.String(120))
    city = db.Column(db.String(120))
    street = db.Column(db.String(120))
    house_number = db.Column(db.String(20))
    password_hash = db.Column(db.String(200))
    auth_method = db.Column(db.String(20))  # 'password', 'google'
    profile_picture = db.Column(db.String(200))  # filename of uploaded picture
    bio = db.Column(db.Text)
    profession = db.Column(db.String(120))
    telephone = db.Column(db.String(20))
    joined_events = db.relationship('EventJoin', backref='user', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'state': self.state,
            'city': self.city,
            'street': self.street,
            'house_number': self.house_number,
            'auth_method': self.auth_method,
            'profile_picture': self.profile_picture,
            'bio': self.bio,
            'profession': self.profession
            # Note: email and telephone are hidden from other users
        }


class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    location = db.Column(db.String(120), nullable=False)
    exact_location = db.Column(db.String(255))
    maps_link = db.Column(db.String(500))
    ticket_price = db.Column(db.String(180))
    transport = db.Column(db.Text)
    source_url = db.Column(db.String(500))
    language = db.Column(db.String(120))
    category = db.Column(db.String(60))
    joined_users = db.relationship('EventJoin', backref='event', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'date': self.date,
            'location': self.location,
            'exact_location': self.exact_location,
            'maps_link': self.maps_link,
            'ticket_price': self.ticket_price,
            'transport': self.transport,
            'source_url': self.source_url,
            'language': self.language,
            'category': self.category,
            'attendees': [ej.user.name for ej in self.joined_users]
        }


class EventJoin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)


NRW_EVENTS = [
    {
        'title': 'Essen Original Festival 2026',
        'date': '2026-05-08 to 2026-05-10',
        'location': 'Essen',
        'exact_location': 'Kennedyplatz, 45127 Essen',
        'maps_link': 'https://www.google.com/maps/search/?api=1&query=Kennedyplatz%2C%2045127%20Essen',
        'ticket_price': 'Free admission',
        'transport': 'Essen Hbf, Hirschlandplatz and Rathaus Essen stops are nearby; city-centre U-Bahn, tram and bus routes give accessible onward travel.',
        'source_url': 'https://www.visitessen.de/essentourismus_veranstaltungen/essen_original_/startseite_10/startseite.de.html',
        'language': 'English-friendly',
        'category': 'Music',
    },
    {
        'title': 'Ruhrfestspiele Recklinghausen 2026',
        'date': '2026-05-01 to 2026-06-14',
        'location': 'Recklinghausen',
        'exact_location': 'Ruhrfestspielhaus, Otto-Burrmeister-Allee 1, 45657 Recklinghausen',
        'maps_link': 'https://www.google.com/maps/search/?api=1&query=Ruhrfestspielhaus%2C%20Otto-Burrmeister-Allee%201%2C%2045657%20Recklinghausen',
        'ticket_price': 'Ticket prices vary by performance',
        'transport': 'Recklinghausen Hbf connects to local buses toward Ruhrfestspielhaus; use the venue stop for the shortest accessible route.',
        'source_url': 'https://www.recklinghausen.de/inhalte/startseite/ruhrfestspiele_kultur/ruhrfestspiele/index.asp',
        'language': 'German; selected international productions',
        'category': 'Cultural',
    },
    {
        'title': 'Rock Hard Festival 2026',
        'date': '2026-05-22 to 2026-05-24',
        'location': 'Gelsenkirchen',
        'exact_location': 'Amphitheater Gelsenkirchen, Grothusstrasse 201, 45883 Gelsenkirchen',
        'maps_link': 'https://www.google.com/maps/search/?api=1&query=Amphitheater%20Gelsenkirchen%2C%20Grothusstrasse%20201%2C%2045883%20Gelsenkirchen',
        'ticket_price': 'Festival ticket from EUR 157.15; with camping from EUR 211.65',
        'transport': 'Use Gelsenkirchen Hbf plus tram/bus toward Nordsternpark/Schloss Horst, then the signed accessible route to the amphitheater.',
        'source_url': 'https://www.metaltix.com/rock-hard-2026-tickets-38181.html',
        'language': 'English-friendly',
        'category': 'Music',
    },
    {
        'title': 'DoKomi 2026',
        'date': '2026-05-29 to 2026-05-31',
        'location': 'Dusseldorf',
        'exact_location': 'Messe Duesseldorf, Stockumer Kirchstrasse 61, 40474 Duesseldorf',
        'maps_link': 'https://www.google.com/maps/search/?api=1&query=Messe%20Duesseldorf%2C%20Stockumer%20Kirchstrasse%2061%2C%2040474%20Duesseldorf',
        'ticket_price': 'From EUR 40 Friday, EUR 47 Saturday, EUR 45 Sunday; 3-day pass EUR 95',
        'transport': 'U78 to Merkur Spiel-Arena/Messe Nord, U78/U79 to Messe Ost/Stockumer Kirchstrasse, or bus 722 to Messe-Center; VRR ticket is included separately with admission.',
        'source_url': 'https://www.dokomi.de/en/event/when-and-where',
        'language': 'English-friendly',
        'category': 'Cultural',
    },
    {
        'title': 'IEM Cologne Major 2026',
        'date': '2026-06-18 to 2026-06-21',
        'location': 'Cologne',
        'exact_location': 'LANXESS arena, Willy-Brandt-Platz 3, 50679 Koeln',
        'maps_link': 'https://www.google.com/maps/search/?api=1&query=LANXESS%20arena%2C%20Willy-Brandt-Platz%203%2C%2050679%20Koeln',
        'ticket_price': 'One-day playoff tickets from EUR 44 to EUR 129; four-day passes from EUR 199 to EUR 999 when available',
        'transport': 'Koeln Messe/Deutz station is about a 10-minute accessible walk from the arena; Stadtbahn and regional rail stop nearby.',
        'source_url': 'https://www.lanxess-arena.de/eventdetail/1240',
        'language': 'English-friendly',
        'category': 'Sports',
    },
    {
        'title': 'Bochum Total 2026',
        'date': '2026-07-02 to 2026-07-05',
        'location': 'Bochum',
        'exact_location': 'Dr.-Ruer-Platz and Bermuda3Eck, 44787 Bochum',
        'maps_link': 'https://www.google.com/maps/search/?api=1&query=Dr.-Ruer-Platz%2C%2044787%20Bochum',
        'ticket_price': 'Free admission',
        'transport': 'Bochum Hbf is close by; tram 308/318 to Bermuda3Eck/Musikforum is the shortest accessible public transport connection.',
        'source_url': 'https://www.ruhr-tourismus.de/en/event/bochum-total/',
        'language': 'English-friendly',
        'category': 'Music',
    },
    {
        'title': 'ColognePride Street Festival 2026',
        'date': '2026-07-03 to 2026-07-05',
        'location': 'Cologne',
        'exact_location': 'Heumarkt and Alter Markt, 50667 Koeln',
        'maps_link': 'https://www.google.com/maps/search/?api=1&query=Heumarkt%2C%2050667%20Koeln',
        'ticket_price': 'Free admission',
        'transport': 'KVB Heumarkt station and Koeln Hbf are nearby; use central Cologne tram, U-Bahn and regional rail connections.',
        'source_url': 'https://www.colognepride.de/en/colognepride-2026',
        'language': 'English-friendly',
        'category': 'Cultural',
    },
    {
        'title': 'Rheinkirmes Duesseldorf 2026',
        'date': '2026-07-17 to 2026-07-26',
        'location': 'Dusseldorf',
        'exact_location': 'Rheinwiesen Oberkassel, Kaiser-Wilhelm-Ring 49, 40545 Duesseldorf',
        'maps_link': 'https://www.google.com/maps/search/?api=1&query=Kaiser-Wilhelm-Ring%2049%2C%2040545%20Duesseldorf',
        'ticket_price': 'Free entry; ride prices paid individually',
        'transport': 'Rheinbahn U70/U74/U75/U76/U77 and buses serve Oberkassel; use Luegplatz or Tonhalle routes depending on bridge access.',
        'source_url': 'https://www.nrw-tourismus.de/events/rheinkirmes-duesseldorf',
        'language': 'English-friendly',
        'category': 'Cultural',
    },
    {
        'title': 'Juicy Beats Festival 2026',
        'date': '2026-07-25',
        'location': 'Dortmund',
        'exact_location': 'Westfalenpark Dortmund, An der Buschmuehle 3, 44139 Dortmund',
        'maps_link': 'https://www.google.com/maps/search/?api=1&query=Westfalenpark%20Dortmund%2C%20An%20der%20Buschmuehle%203%2C%2044139%20Dortmund',
        'ticket_price': 'Early bird EUR 59; Phase 2 EUR 70; children up to 10 free',
        'transport': 'Dortmund Hbf connects to U45/U49 toward Westfalenpark; use Westfalenpark or Westfalenhallen stops for accessible entry routes.',
        'source_url': 'https://www.juicybeats.net/en/news/juicy-beats-2026-is-happening/',
        'language': 'English-friendly',
        'category': 'Music',
    },
    {
        'title': 'Cranger Kirmes 2026',
        'date': '2026-07-31 to 2026-08-10',
        'location': 'Herne',
        'exact_location': 'Cranger Kirmesplatz, Dorstener Strasse 476, 44653 Herne',
        'maps_link': 'https://www.google.com/maps/search/?api=1&query=Cranger%20Kirmesplatz%2C%20Dorstener%20Strasse%20476%2C%2044653%20Herne',
        'ticket_price': 'Free entry; ride prices paid individually',
        'transport': 'Regular buses run from Wanne-Eickel Hbf and Herne Bf to Cranger Kirmes; use the Heerstrasse, Florastrasse or Dorstener Strasse stops.',
        'source_url': 'https://cranger-kirmes.de/',
        'language': 'English-friendly',
        'category': 'Cultural',
    },
    {
        'title': 'Koelner Lichter 2026',
        'date': '2026-08-01',
        'location': 'Cologne',
        'exact_location': 'Rhine riverbanks near Rheinpark, Rheinparkweg 1, 50679 Koeln',
        'maps_link': 'https://www.google.com/maps/search/?api=1&query=Rheinparkweg%201%2C%2050679%20Koeln',
        'ticket_price': 'Public riverside viewing is free; ship, rooftop and hospitality tickets vary by provider',
        'transport': 'Koeln Messe/Deutz and KVB Deutz/Messe are nearby; use S-Bahn, regional rail and tram connections around the Rhine closures.',
        'source_url': 'https://www.koeln.de/veranstaltungen/koelner-lichter/',
        'language': 'English-friendly',
        'category': 'Cultural',
    },
    {
        'title': 'Gamescom 2026',
        'date': '2026-08-26 to 2026-08-30',
        'location': 'Cologne',
        'exact_location': 'Koelnmesse, Messeplatz 1, 50679 Koeln',
        'maps_link': 'https://www.google.com/maps/search/?api=1&query=Koelnmesse%2C%20Messeplatz%201%2C%2050679%20Koeln',
        'ticket_price': 'Day tickets EUR 31.50 Thu/Fri/Sun, EUR 41 Saturday; Wednesday wildcard EUR 65.50',
        'transport': 'Koeln Messe/Deutz station and Koelnmesse Stadtbahn stops serve the fair; S6, S11, S12 and S19 stop nearby.',
        'source_url': 'https://www.koeln.de/event/gamescom/',
        'language': 'English-friendly',
        'category': 'Education',
    },
    {
        'title': 'FEI World Championships Aachen 2026',
        'date': '2026-08-11 to 2026-08-23',
        'location': 'Aachen',
        'exact_location': 'Allianz Park, Albert-Servais-Allee 50, 52070 Aachen',
        'maps_link': 'https://www.google.com/maps/search/?api=1&query=Allianz%20Park%2C%20Albert-Servais-Allee%2050%2C%2052070%20Aachen',
        'ticket_price': 'Event tickets from EUR 20; many categories vary by discipline and stand',
        'transport': 'All event tickets include same-day round-trip travel to/from the Soers grounds on ASEAG bus lines, except APAG shuttle.',
        'source_url': 'https://www.aachen2026.com/',
        'language': 'English-friendly',
        'category': 'Sports',
    },
    {
        'title': 'Zeltfestival Ruhr 2026',
        'date': '2026-08-21 to 2026-09-06',
        'location': 'Bochum',
        'exact_location': 'Kemnader See, Querenburger Strasse 35, 58455 Witten',
        'maps_link': 'https://www.google.com/maps/search/?api=1&query=Querenburger%20Strasse%2035%2C%2058455%20Witten',
        'ticket_price': 'Festival area EUR 5 presale or EUR 7 box office; concert/show tickets vary',
        'transport': 'Bogestra cooperation includes VRR travel on the event day for concert ticket holders; buses serve Kemnader See/Heven.',
        'source_url': 'https://www.zeltfestivalruhr.de/service/faq/',
        'language': 'English-friendly',
        'category': 'Music',
    },
    {
        'title': 'Puetzchens Markt 2026',
        'date': '2026-09-11 to 2026-09-15',
        'location': 'Bonn',
        'exact_location': 'Marktwiesen Puetzchen, Puetzchens Chaussee, 53229 Bonn',
        'maps_link': 'https://www.google.com/maps/search/?api=1&query=Marktwiesen%20Puetzchen%2C%20Puetzchens%20Chaussee%2C%2053229%20Bonn',
        'ticket_price': 'Free admission; ride prices paid individually',
        'transport': 'Use Bonn Hbf or Bonn-Beuel with SWB/VRS fair buses and shuttle services toward Puetzchen.',
        'source_url': 'https://www.nrw-tourism.com/events/puetzchens-markt-fair',
        'language': 'English-friendly',
        'category': 'Cultural',
    },
    {
        'title': 'SPIEL Essen 2026',
        'date': '2026-10-22 to 2026-10-25',
        'location': 'Essen',
        'exact_location': 'Messe Essen, Messeplatz 1, 45131 Essen',
        'maps_link': 'https://www.google.com/maps/search/?api=1&query=Messe%20Essen%2C%20Messeplatz%201%2C%2045131%20Essen',
        'ticket_price': '2026 shop opens summer 2026; 2025 adult day ticket was EUR 23.50 regular',
        'transport': 'Essen Hbf connects by U11 to Messe Ost/Gruga and Messe West/Sued; fairground stations provide accessible entry routes.',
        'source_url': 'https://www.spiel-essen.de/en/visit/tickets-opening-hours',
        'language': 'English-friendly',
        'category': 'Education',
    },
]


def ensure_event_columns():
    existing_columns = {
        row[1]
        for row in db.session.execute(text("PRAGMA table_info(event)")).fetchall()
    }
    columns = {
        'exact_location': 'VARCHAR(255)',
        'maps_link': 'VARCHAR(500)',
        'ticket_price': 'VARCHAR(180)',
        'transport': 'TEXT',
        'source_url': 'VARCHAR(500)',
    }

    for column, column_type in columns.items():
        if column not in existing_columns:
            db.session.execute(text(f"ALTER TABLE event ADD COLUMN {column} {column_type}"))

    db.session.commit()


def seed_nrw_events():
    seeded_titles = {event['title'] for event in NRW_EVENTS}

    for event_data in NRW_EVENTS:
        event = Event.query.filter_by(title=event_data['title']).first()
        if event is None:
            event = Event(**event_data)
            db.session.add(event)
        else:
            for key, value in event_data.items():
                setattr(event, key, value)

    for stale_event in Event.query.filter(~Event.title.in_(seeded_titles)).all():
        db.session.delete(stale_event)

    db.session.commit()


def init_db():
    """Initialize database and seed NRW events without deleting user accounts."""
    with app.app_context():
        db.create_all()
        ensure_event_columns()
        
        # Ensure upload folder exists
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        seed_nrw_events()


def auth_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if 'user_id' not in session and 'guest' not in session:
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    return wrapped_view


def get_current_user():
    """Get current user from database"""
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None


@app.route('/')
@auth_required
def index():
    user = get_current_user()
    guest = session.get('guest')
    events = Event.query.order_by(Event.date.asc()).all()
    joined_event_ids = [ej.event_id for ej in user.joined_events] if user else []
    
    return render_template(
        'index.html',
        events=[e.to_dict() for e in events],
        user=user.to_dict() if user else None,
        guest=guest,
        joined_events=joined_event_ids
    )


@app.route('/join/<int:event_id>')
@auth_required
def join_event(event_id):
    if session.get('guest'):
        return redirect(url_for('login'))
    
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))
    
    event = Event.query.get(event_id)
    if not event:
        return "Event not found", 404
    
    # Check if already joined
    existing_join = EventJoin.query.filter_by(user_id=user.id, event_id=event_id).first()
    if not existing_join:
        join = EventJoin(user_id=user.id, event_id=event_id)
        db.session.add(join)
        db.session.commit()
    
    return redirect(url_for('find_people', event_id=event_id))


@app.route('/login')
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    return render_template(
        'login.html',
        google_enabled=bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
        user=None,
        guest=session.get('guest')
    )


@app.route('/login/guest', methods=['GET', 'POST'])
def login_guest():
    if request.method != 'POST' or request.form.get('accept_terms') != 'on':
        return render_template(
            'login.html',
            google_enabled=bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
            error='Please accept the Terms and Conditions before continuing as Guest.',
            user=None,
            guest=None
        )

    session['guest'] = True
    session.pop('user_id', None)
    return redirect(url_for('index'))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        state = request.form.get('state', '').strip()
        city = request.form.get('city', '').strip()
        street = request.form.get('street', '').strip()
        house_number = request.form.get('house_number', '').strip()
        password = request.form.get('password', '').strip()
        bio = request.form.get('bio', '').strip()
        profession = request.form.get('profession', '').strip()
        telephone = request.form.get('telephone', '').strip()
        accept_terms = request.form.get('accept_terms') == 'on'

        if not (first_name and last_name and state and street and house_number and password):
            return render_template('signup.html', error='Please fill in all required fields.')

        if not accept_terms:
            return render_template('signup.html', error='Please accept the Terms and Conditions to create an account.')

        if state == 'North Rhine-Westphalia' and not city:
            return render_template('signup.html', error='Please select a city for North Rhine-Westphalia.')

        full_name = f'{first_name} {last_name}'
        
        # Handle profile picture upload
        profile_picture_filename = None
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename:
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                profile_picture_filename = filename

        # Create new user
        user = User(
            name=full_name,
            first_name=first_name,
            last_name=last_name,
            state=state,
            city=city,
            street=street,
            house_number=house_number,
            password_hash=generate_password_hash(password),
            auth_method='password',
            profile_picture=profile_picture_filename,
            bio=bio,
            profession=profession,
            telephone=telephone
        )
        db.session.add(user)
        db.session.commit()
        
        session['user_id'] = user.id
        session.pop('guest', None)
        return redirect(url_for('index'))

    return render_template('signup.html')


@app.route('/login/google')
def login_google():
    session.pop('guest', None)
    if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
        redirect_uri = url_for('authorize', _external=True)
        return oauth.google.authorize_redirect(redirect_uri)

    return render_template('login.html', google_enabled=False, error='Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to enable login.')


@app.route('/login/manual', methods=['POST'])
def login_manual():
    name = request.form.get('name', '').strip()
    password = request.form.get('password', '').strip()

    users = User.query.filter_by(name=name, auth_method='password').all()
    user = next(
        (candidate for candidate in users if candidate.password_hash and check_password_hash(candidate.password_hash, password)),
        None
    )
    
    if user:
        session['user_id'] = user.id
        session.pop('guest', None)
        return redirect(url_for('index'))
    else:
        return render_template(
            'login.html',
            google_enabled=bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
            error='Invalid name or password.',
            user=None,
            guest=None
        )


@app.route('/auth')
def authorize():
    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET):
        return render_template('login.html', google_enabled=False, error='Google OAuth is not configured. Contact the app owner to enable login.')

    token = oauth.google.authorize_access_token()
    user_info = oauth.google.get('userinfo').json()
    
    # Check if user exists
    user = User.query.filter_by(email=user_info.get('email')).first()
    
    if not user:
        # Create new user from Google
        user = User(
            email=user_info.get('email'),
            name=user_info.get('name'),
            first_name=user_info.get('given_name', ''),
            last_name=user_info.get('family_name', ''),
            auth_method='google'
        )
        db.session.add(user)
        db.session.commit()
    
    session['user_id'] = user.id
    session.pop('guest', None)
    return redirect(url_for('index'))


@app.route('/profile', methods=['GET', 'POST'])
@auth_required
def profile():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        bio = request.form.get('bio', '').strip()
        profession = request.form.get('profession', '').strip()
        telephone = request.form.get('telephone', '').strip()
        
        # Handle profile picture upload
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename:
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                user.profile_picture = filename
        
        user.bio = bio
        user.profession = profession
        user.telephone = telephone
        db.session.commit()
        
        return redirect(url_for('profile'))
    
    return render_template('profile.html', user=user)


@app.route('/find_people/<int:event_id>')
@auth_required
def find_people(event_id):
    event = Event.query.get(event_id)
    
    if not event:
        return "Event not found", 404
    
    user = get_current_user()
    guest = session.get('guest')
    
    joined = False
    if user:
        join = EventJoin.query.filter_by(user_id=user.id, event_id=event_id).first()
        joined = join is not None
    
    # Hide attendees for guests
    if guest:
        attendees = []
    else:
        attendees = [ej.user.to_dict() for ej in event.joined_users]
    
    return render_template(
        'find_people.html',
        event=event.to_dict(),
        user=user.to_dict() if user else None,
        guest=guest,
        joined=joined,
        attendees=attendees
    )


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
