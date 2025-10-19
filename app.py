
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from authlib.integrations.flask_client import OAuth
from jose import jwt
from urllib.request import urlopen
import json
from fpdf import FPDF
import os
from dotenv import load_dotenv
import authlib
import authlib.jose.errors
import requests
from io import BytesIO
import re
from pdf2image import convert_from_path
import sqlitecloud
import google.generativeai as genai


# Load environment variables from .env
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'changeme')
oauth = OAuth(app)

# Configure Gemini AI
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash-exp')

# Auth0 configuration
app.config['AUTH0_CLIENT_ID'] = os.environ.get('AUTH0_CLIENT_ID')
app.config['AUTH0_CLIENT_SECRET'] = os.environ.get('AUTH0_CLIENT_SECRET')
app.config['AUTH0_DOMAIN'] = os.environ.get('AUTH0_DOMAIN')
app.config['AUTH0_CALLBACK_URL'] = os.environ.get('AUTH0_CALLBACK_URL')
AUTH0_DOMAIN = os.environ.get('AUTH0_DOMAIN')
API_AUDIENCE = os.environ.get('API_AUDIENCE')
ISSUER = os.environ.get('ISSUER')
ALGORITHMS = [os.environ.get('ALGORITHMS', 'RS256')]

auth0 = oauth.register(
    'auth0',
    client_id=app.config['AUTH0_CLIENT_ID'],
    client_secret=app.config['AUTH0_CLIENT_SECRET'],
    api_base_url=f"https://{app.config['AUTH0_DOMAIN']}",
    access_token_url=f"https://{app.config['AUTH0_DOMAIN']}/oauth/token",
    authorize_url=f"https://{app.config['AUTH0_DOMAIN']}/authorize",
    client_kwargs={'scope': 'openid profile email'},
    jwks_uri=f'https://{app.config["AUTH0_DOMAIN"]}/.well-known/jwks.json'
)

def render_images(text):
    return re.sub(r'\[img](https?://[^\s]+)', r'<img src="\1" alt="This image is already part of the lesson" style="max-width: 100%; margin: 10px 0;">', text)

# Register filter in Jinja
app.jinja_env.filters['render_images'] = render_images

def generate_pdf(title, content):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=14)
    
    lines = content.split("\n")
    for line in lines:
        if line.startswith("[img]"):
            img_url = line.replace("[img]", "").strip()
            try:
                response = requests.get(img_url)
                if response.status_code == 200:
                    img = BytesIO(response.content)
                    pdf.image(img, x=10, w=170)
                else:
                    pdf.multi_cell(0, 10, f"[Image Failed to Load: {img_url}]")
            except Exception as e:
                pdf.multi_cell(0, 10, f"[Invalid Image URL: {img_url}]")
        else:
            pdf.multi_cell(0, 10, line)

    pdf_file = f"static/lesson_{title.replace(' ', '_')}.pdf"
    pdf.output(pdf_file)
    return pdf_file

def get_jwks():
    url = f'https://{AUTH0_DOMAIN}/.well-known/jwks.json'
    response = urlopen(url)
    return json.loads(response.read())

def verify_token(token):
    jwks = get_jwks()
    unverified_header = jwt.get_unverified_header(token)
    
    rsa_key = {}
    for key in jwks['keys']:
        if key['kid'] == unverified_header['kid']:
            rsa_key = {
                'kty': key['kty'],
                'kid': key['kid'],
                'use': key['use'],
                'n': key['n'],
                'e': key['e']
            }
    
    if rsa_key:
        try:
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=ALGORITHMS,
                audience=API_AUDIENCE,
                issuer=ISSUER
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise Exception('Token expired.')
        except jwt.JWTClaimsError:
            raise Exception('Incorrect claims.')
        except Exception:
            raise Exception('Invalid token.')
    raise Exception('Unable to find appropriate key.')

# db setup
def init_db():
    connection_string = 'sqlitecloud://cl7vyaxhhz.g4.sqlite.cloud:8860/database.db?apikey=jnNrwbq16JcWWEWJcmTn25I5Nz1kMlbgovCQBvbPf3k'
    db = sqlitecloud.connect(connection_string)
    
    # Create the simulations table if it doesn't exist
    db.execute('''CREATE TABLE IF NOT EXISTS simulations (
                    id INTEGER PRIMARY KEY, 
                    title TEXT, 
                    link TEXT, 
                    description TEXT,
                    solution_link TEXT, 
                    grade INTEGER)''')
    
    # Create other tables
    db.execute('''CREATE TABLE IF NOT EXISTS lessons (id INTEGER PRIMARY KEY, title TEXT, content TEXT, grade INTEGER)''')
    db.execute('''CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY, message TEXT, email TEXT)''')
    
    # Create interactive lessons table
    db.execute('''CREATE TABLE IF NOT EXISTS interactive_lessons (
                    id INTEGER PRIMARY KEY, 
                    title TEXT, 
                    content TEXT, 
                    grade INTEGER,
                    cad_file_url TEXT,
                    quiz_questions TEXT)''')
    
    # Create quiz results table
    db.execute('''CREATE TABLE IF NOT EXISTS quiz_results (
                    id INTEGER PRIMARY KEY,
                    lesson_id INTEGER,
                    user_email TEXT,
                    score INTEGER,
                    total_questions INTEGER,
                    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (lesson_id) REFERENCES interactive_lessons (id))''')
       
def get_db():
    connection_string = 'sqlitecloud://cl7vyaxhhz.g4.sqlite.cloud:8860/database.db?apikey=jnNrwbq16JcWWEWJcmTn25I5Nz1kMlbgovCQBvbPf3k'
    db = sqlitecloud.connect(connection_string)
    db.row_factory = sqlitecloud.Row  # This is similar to sqlite3's Row factory
    return db

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/login')
def login():
    #generate nonce and store it in session
    nonce = os.urandom(16).hex()
    session['nonce'] = nonce
    
    # Redirect to Auth0 login if not logged in
    return auth0.authorize_redirect(redirect_uri=url_for('callback', _external=True), nonce=nonce, prompt='login')

@app.route('/signup')
def signup():
    return redirect(url_for('login'))

@app.route('/callback')
def callback():
    try:
        token = auth0.authorize_access_token()
        nonce = session.get('nonce')

        if not nonce:
            return "Error: Nonce missing. Please try logging in again.", 400
        
        # Validate the ID token
        user = auth0.parse_id_token(token, nonce=nonce)
        session['user'] = user  # Store user info
        session.pop('nonce', None)  # Remove nonce after use
        
        if user.get('email') == 'david.constantinescu1982@gmail.com' or user.get('email') == 'rookielab@gmail.com':
            session['is_admin'] = True

        return redirect(url_for('home'))
    except authlib.jose.errors.InvalidClaimError as e:
        return f"Invalid claim: {str(e)}", 400
    except Exception as e:
        return f"Login failed: {str(e)}", 400

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out!')
    return redirect('/')

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if 'user' not in session or not session.get('is_admin'):
        flash("You don't have permission to access this page.")
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        title = request.form['title']
        link = request.form['link']
        solution_link = request.form['solution_link']
        description = request.form['description']
        grade = 8
        if not title or not link or not description:
            flash('All fields are required!')
            return redirect(url_for('admin'))
        
        db = get_db()
        db.execute("INSERT INTO simulations (title, link, description, solution_link, grade) VALUES (?, ?, ?, ?, ?)", (title, link, description, solution_link, grade))
        flash('Interactive lesson uploaded successfully!')
    
    db = get_db()
    feedback = db.execute("SELECT * FROM feedback").fetchall()

    return render_template('admin.html', is_admin=session.get('is_admin', False), feedback=feedback)


@app.route('/simulari')
def simulari():
    db = get_db()
    simulations = db.execute("SELECT * FROM simulations").fetchall()
    
    return render_template('interactive.html', simulations=simulations)

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        message = request.form['message']
        email = request.form['email']
        db = get_db()
        db.execute("INSERT INTO feedback (message, email) VALUES (?, ?)", (message, email))
        flash('Feedback trimis!')
    return render_template('contact.html')

@app.route('/admin/lessons', methods=['GET', 'POST'])
def add_lesson():
    if 'user' not in session or not session.get('is_admin'):
        flash("You don't have permission to access this page.")
        return redirect(url_for('home'))

    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        grade = request.form['grade']
        
        # Store the lesson in the database
        db = get_db()
        db.execute("INSERT INTO lessons (title, content, grade) VALUES (?, ?, ?)", (title, content, grade))
        flash('Lecția a fost adăugată cu succes!')
        return redirect(url_for('add_lesson'))

    # Retrieve lessons in reverse chronological order
    db = get_db()
    lessons = db.execute("SELECT * FROM lessons ORDER BY id DESC").fetchall()

    # Render template with lessons
    return render_template('admin_lessons.html', lessons=lessons, is_admin=session.get('is_admin', False))

@app.route('/admin/interactive-lessons', methods=['GET', 'POST'])
def add_interactive_lesson():
    if 'user' not in session or not session.get('is_admin'):
        flash("You don't have permission to access this page.")
        return redirect(url_for('home'))

    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        grade = request.form['grade']
        cad_file_url = request.form.get('cad_file_url', '')
        
        # Process quiz questions
        quiz_questions = []
        question_count = int(request.form.get('question_count', 0))
        
        for i in range(question_count):
            question_text = request.form.get(f'question_{i}')
            if question_text:
                options = []
                for j in range(4):  # 4 options per question
                    option = request.form.get(f'question_{i}_option_{j}')
                    if option:
                        options.append(option)
                
                correct_answer = int(request.form.get(f'question_{i}_correct', 0))
                
                if len(options) >= 2:  # At least 2 options required
                    quiz_questions.append({
                        'question': question_text,
                        'options': options,
                        'correct_answer': correct_answer
                    })
        
        # Store the interactive lesson in the database
        db = get_db()
        import json
        quiz_json = json.dumps({'questions': quiz_questions})
        db.execute("INSERT INTO interactive_lessons (title, content, grade, cad_file_url, quiz_questions) VALUES (?, ?, ?, ?, ?)", 
                   (title, content, grade, cad_file_url, quiz_json))
        flash('Interactive lesson added successfully!')
        return redirect(url_for('add_interactive_lesson'))

    # Retrieve interactive lessons in reverse chronological order
    db = get_db()
    interactive_lessons = db.execute("SELECT * FROM interactive_lessons ORDER BY id DESC").fetchall()

    # Render template with interactive lessons
    return render_template('admin_interactive_lessons.html', interactive_lessons=interactive_lessons, is_admin=session.get('is_admin', False))

@app.route('/lessons/<int:lesson_id>')
def view_lesson(lesson_id):
    db = get_db()
    lesson = db.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
    if lesson is None:
        return "Lecția nu a fost găsită.", 404
    return render_template('view_lesson.html', lesson=lesson)

@app.route('/lessons/<int:lesson_id>/pdf')
def generate_lesson_pdf(lesson_id):
    if 'user' not in session:
        flash("Trebuie să fiți autentificat pentru a descărca PDF-ul.")
        return redirect(url_for('login'))
    
    db = get_db()
    lesson = db.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
    if lesson is None:
        return "Lecția nu a fost găsită.", 404

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=14)
    
    lines = lesson[2].split("\n")
    for line in lines:
        if line.startswith("[img]"):
            img_url = line.replace("[img]", "").strip()
            try:
                response = requests.get(img_url)
                if response.status_code == 200:
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix='.jpg') as tmp:
                        tmp.write(response.content)
                        tmp.flush()
                        pdf.image(tmp.name, x=10, w=170)
                else:
                    pdf.multi_cell(0, 10, f"[Image Failed to Load: {img_url}]")
            except Exception as e:
                pdf.multi_cell(0, 10, f"[Invalid Image URL: {img_url}]")
        else:
            pdf.multi_cell(0, 10, line)

    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        pdf.output(tmp.name)
        buffer = BytesIO()
        with open(tmp.name, 'rb') as f:
            buffer.write(f.read())
        buffer.seek(0)
        os.remove(tmp.name)

    return send_file(buffer, as_attachment=True, download_name=f"lecția_{lesson[1]}.pdf", mimetype='application/pdf')

@app.route('/lessons', methods=['GET'])
def lessons():
    grade = request.args.get('grade', type=int)  # Get the grade from the query parameter
    db = get_db()
    if grade:
        # Filter lessons by grade if a grade is provided
        lessons = db.execute("SELECT id, title, SUBSTR(content, 1, 500) AS content, grade FROM lessons WHERE grade = ? ORDER BY id DESC", (grade,)).fetchall()
    else:
        # Fetch all lessons if no grade is provided
        lessons = db.execute("SELECT id, title, SUBSTR(content, 1, 500) AS content, grade FROM lessons ORDER BY id DESC").fetchall()
    
    return render_template('lessons.html', lessons=lessons)

@app.route('/simulare/<int:simul_id>')
def simulare_view(simul_id):
    db = get_db()
    simulare = db.execute("SELECT * FROM simulations WHERE id = ?", (simul_id,)).fetchone()
    if simulare is None:
        return "Simularea nu a fost găsită.", 404

    link = simulare['link']
    solution_link = simulare['solution_link']
    
    is_logged_in = 'user' in session

    if not is_logged_in:
        image_path = f'images/simul_{simul_id}_first_page.png'
        full_image_path = os.path.join('static', image_path)
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(full_image_path), exist_ok=True)
        
        # Download and convert the PDF if the image doesn't exist
        if not os.path.exists(full_image_path):
            temp_pdf_path = os.path.join('static/temp', f'simul_{simul_id}.pdf')
            os.makedirs(os.path.dirname(temp_pdf_path), exist_ok=True)

            try:
                # Download the PDF from the link
                response = requests.get(link)
                response.raise_for_status()

                with open(temp_pdf_path, 'wb') as pdf_file:
                    pdf_file.write(response.content)

                # Convert first page to image
                pages = convert_from_path(temp_pdf_path, first_page=1, last_page=1)
                pages[0].save(full_image_path, 'PNG')

                # Clean up temporary PDF
                os.remove(temp_pdf_path)

            except requests.exceptions.RequestException as e:
                flash("Eroare la descărcarea fișierului PDF.")
                return redirect(url_for('simulari'))
            except Exception as e:
                flash("Eroare la procesarea fișierului PDF.")
                return redirect(url_for('simulari'))

        return render_template('interactive_view.html', title="Simulare", simul_id=simul_id, 
                               link=link, solution_link=solution_link, is_logged_in=is_logged_in,
                               image_path=image_path)
    
    return render_template('interactive_view.html', title="Simulare", simul_id=simul_id, 
                           link=link, solution_link=solution_link, is_logged_in=is_logged_in)
    
@app.route('/download_simul/<int:simul_id>')
def download_simul(simul_id):
    db = get_db()
    simulare = db.execute("SELECT * FROM simulations WHERE id = ?", (simul_id,)).fetchone()

    if simulare is None:
        flash("Simularea nu a fost găsită.")
        return redirect(url_for('simulari'))

    # Get the simulation document link
    link = simulare[2]
    if not link or not link.startswith('http'):
        flash("Invalid simulation link.")
        return redirect(url_for('simulari'))

    return redirect(link)  # Redirect to the simulation file URL for downloading

@app.route('/download_solution/<int:simul_id>')
def download_solution(simul_id):
    db = get_db()
    simulare = db.execute("SELECT * FROM simulations WHERE id = ?", (simul_id,)).fetchone()

    if simulare is None:
        flash("Simularea nu a fost găsită.")
        return redirect(url_for('simulari'))

    # Get the solution document link
    solution_link = simulare[4]
    if not solution_link or not solution_link.startswith('http'):
        flash("Invalid solution link.")
        return redirect(url_for('simulari'))

    # Allow downloading only for logged-in users
    if 'user' not in session:
        flash("Trebuie să fiți autentificat pentru a descărca soluția.")
        return redirect(url_for('interactive_view', simul_id=simul_id))

    return redirect(solution_link)  # Redirect to the solution file URL for downloading

@app.route('/policy')
def policy():
    return render_template('policy.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/interactive-lessons', methods=['GET'])
def interactive_lessons():
    grade = request.args.get('grade', type=int)  # Get the grade from the query parameter
    db = get_db()
    if grade:
        # Filter interactive lessons by grade if a grade is provided
        lessons = db.execute("SELECT id, title, SUBSTR(content, 1, 500) AS content, grade, cad_file_url FROM interactive_lessons WHERE grade = ? ORDER BY id DESC", (grade,)).fetchall()
    else:
        # Fetch all interactive lessons if no grade is provided
        lessons = db.execute("SELECT id, title, SUBSTR(content, 1, 500) AS content, grade, cad_file_url FROM interactive_lessons ORDER BY id DESC").fetchall()
    
    return render_template('interactive_lessons.html', interactive_lessons=lessons)

@app.route('/interactive-lesson/<int:lesson_id>')
def view_interactive_lesson(lesson_id):
    db = get_db()
    lesson = db.execute("SELECT * FROM interactive_lessons WHERE id = ?", (lesson_id,)).fetchone()
    if lesson is None:
        return "Interactive lesson not found.", 404
    return render_template('interactive_lesson_view.html', lesson=lesson)

@app.route('/api/quiz/<int:lesson_id>')
def get_quiz(lesson_id):
    db = get_db()
    lesson = db.execute("SELECT quiz_questions FROM interactive_lessons WHERE id = ?", (lesson_id,)).fetchone()
    if lesson is None or not lesson[0]:
        return jsonify({'error': 'No quiz available'}), 404
    
    try:
        import json
        quiz_data = json.loads(lesson[0])
        return jsonify(quiz_data)
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid quiz data'}), 500

@app.route('/api/submit-quiz', methods=['POST'])
def submit_quiz():
    if 'user' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    data = request.get_json()
    lesson_id = data.get('lesson_id')
    score = data.get('score')
    total_questions = data.get('total_questions')
    
    if not all([lesson_id, score is not None, total_questions]):
        return jsonify({'error': 'Missing required data'}), 400
    
    db = get_db()
    user_email = session['user'].get('email', 'unknown')
    
    # Store quiz result
    db.execute("INSERT INTO quiz_results (lesson_id, user_email, score, total_questions) VALUES (?, ?, ?, ?)", 
               (lesson_id, user_email, score, total_questions))
    
    return jsonify({'success': True, 'score': score})

@app.route('/api/cad-proxy/<int:lesson_id>')
def cad_proxy(lesson_id):
    """Proxy endpoint to serve CAD files with proper CORS headers for 3dviewer.net"""
    db = get_db()
    lesson = db.execute("SELECT cad_file_url FROM interactive_lessons WHERE id = ?", (lesson_id,)).fetchone()
    
    if not lesson or not lesson[0]:
        return "CAD file not found", 404
    
    try:
        # Fetch the CAD file from the CDN
        response = requests.get(lesson[0], stream=True)
        response.raise_for_status()
        
        # Create Flask response with proper CORS headers
        from flask import Response
        return Response(
            response.content,
            status=200,
            headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Range',
                'Content-Type': response.headers.get('Content-Type', 'application/octet-stream'),
                'Content-Length': str(len(response.content)),
                'Accept-Ranges': 'bytes'
            }
        )
    except requests.RequestException as e:
        return f"Error fetching CAD file: {str(e)}", 500

@app.route('/api/cad-url/<int:lesson_id>')
def get_cad_url(lesson_id):
    """Get the CAD file URL for a lesson"""
    db = get_db()
    lesson = db.execute("SELECT cad_file_url FROM interactive_lessons WHERE id = ?", (lesson_id,)).fetchone()
    
    if not lesson or not lesson[0]:
        return jsonify({'error': 'CAD file not found'}), 404
    
    return jsonify({'url': lesson[0]})


@app.route('/api/chat-with-gemini', methods=['POST'])
def chat_with_gemini():
    """Handle chat messages with Gemini AI"""
    try:
        data = request.get_json()
        
        lesson_title = data.get('lesson_title', '')
        lesson_content = data.get('lesson_content', '')
        image_urls = data.get('image_urls', [])
        user_message = data.get('user_message', '')
        chat_history = data.get('chat_history', [])
        
        # Build context for Gemini
        context_prompt = f"""
You are an AI assistant helping a student with their lesson. Here's the context:

Lesson Title: {lesson_title}

Lesson Content:
{lesson_content}

Image URLs in the lesson (if any):
{', '.join(image_urls) if image_urls else 'No images'}

Previous conversation history:
"""
        
        # Add chat history to context
        for msg in chat_history[-6:]:  # Keep last 6 messages for context
            role = "Student" if msg['role'] == 'user' else "Assistant"
            context_prompt += f"\n{role}: {msg['content']}"
        
        context_prompt += f"\n\nCurrent student question: {user_message}"
        
        context_prompt += """
Please provide a helpful, educational response based on the lesson content. Be conversational and supportive. If the student asks about something not covered in the lesson, let them know and offer to help with what is covered. Keep responses concise but informative.
"""
        
        # Generate response using Gemini
        response = model.generate_content(context_prompt)
        
        return jsonify({
            'success': True,
            'response': response.text
        })
        
    except Exception as e:
        print(f"Error in Gemini chat: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/account')
def account():
    """Display user account information, progress, and quiz scores"""
    if 'user' not in session:
        flash('Please log in to view your account.')
        return redirect(url_for('login'))
    
    db = get_db()
    user_email = session['user'].get('email', 'unknown')
    user_name = session['user'].get('name', 'Unknown User')
    
    # Get user's quiz results
    quiz_results = db.execute('''
        SELECT qr.lesson_id, il.title as lesson_title, qr.score, qr.total_questions, 
               qr.completed_at
        FROM quiz_results qr
        JOIN interactive_lessons il ON qr.lesson_id = il.id
        WHERE qr.user_email = ?
        ORDER BY qr.completed_at DESC
    ''', (user_email,)).fetchall()
    
    # Calculate learning statistics
    total_quizzes = len(quiz_results)
    total_lessons = db.execute('SELECT COUNT(*) FROM interactive_lessons').fetchone()[0]
    
    if quiz_results:
        # Calculate average score (score is out of 10)
        total_score = sum(result[2] for result in quiz_results)
        average_score = total_score / len(quiz_results)
        best_score = max(result[2] for result in quiz_results)
        
        # Count lessons by department
        department_stats = {}
        for result in quiz_results:
            lesson_id = result[0]
            lesson_info = db.execute('SELECT grade FROM interactive_lessons WHERE id = ?', (lesson_id,)).fetchone()
            if lesson_info:
                grade = lesson_info[0]
                dept_name = {5: 'Marketing', 6: '3D & CAD', 7: 'Hardware', 8: 'Programming'}.get(grade, 'Unknown')
                if dept_name not in department_stats:
                    department_stats[dept_name] = 0
                department_stats[dept_name] += 1
    else:
        average_score = 0
        best_score = 0
        department_stats = {}
    
    return render_template('account.html', 
                         user_name=user_name,
                         user_email=user_email,
                         quiz_results=quiz_results,
                         total_quizzes=total_quizzes,
                         total_lessons=total_lessons,
                         average_score=average_score,
                         best_score=best_score,
                         department_stats=department_stats)

if __name__ == '__main__':
    init_db()
    app.run(host = "0.0.0.0", port = 2014, debug=True)
