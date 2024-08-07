import MySQLdb
from flask import Flask, render_template, redirect, url_for, request, flash, session, request, jsonify
from flask_mysqldb import MySQL
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
import re
import csv
import pandas as pd
from datetime import datetime
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'games_dataset'
games_df = pd.read_csv('games_recommend.csv')

mysql = MySQL(app)
login_manager = LoginManager(app)
login_manager.init_app(app)
login_manager.login_view = 'login'
bcrypt = Bcrypt(app)

class Customer(UserMixin):
    def __init__(self, id, name, email, password, user_profile=None):
        self.id = id
        self.name = name
        self.email = email
        self.password = password
        self.user_profile = user_profile

@login_manager.user_loader
def load_user(user_id):
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT * FROM customers WHERE customerID = %s", (user_id,))
    user = cursor.fetchone()
    if user:
        return Customer(*user)
    return None

@app.route('/logout')
@login_required
def logout():
    logout_user()
    if session.get('was_once_logged_in'):
        # prevent flashing automatically logged out message
        del session['was_once_logged_in']
    flash('You have successfully logged yourself out.')
    return redirect('/login')

@app.route('/')
@login_required
def home():
    cursor = mysql.connection.cursor()
    
    # Fetch top games
    cursor.execute("SELECT app_id, name, header_image FROM game ORDER BY CompositeRating DESC LIMIT 10")
    top_games = cursor.fetchall()
    
    # Fetch recommended games based on user profile
    user_profile = eval(current_user.user_profile) if current_user.user_profile else []
    recommended_games = []
    
    if user_profile:
        recommended_game_ids = get_recommendations(user_profile, current_user.id, top_n=7)
        format_strings = ','.join(['%s'] * len(recommended_game_ids))
        cursor.execute(f"SELECT app_id, name, header_image FROM game WHERE app_id IN ({format_strings})", tuple(recommended_game_ids))
        recommended_games = cursor.fetchall()
    
    cursor.close()
    
    return render_template('home.html', top_games=top_games, recommended_games=recommended_games, customer=current_user)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm-password']

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM customers WHERE email = %s", (email,))
        user = cursor.fetchone()

        if user:
            flash('*Email is already registered', 'danger')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('*Password and Confirm Password are not same', 'danger')
            return render_template('register.html')

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        cursor.execute("INSERT INTO customers (name, email, password) VALUES (%s, %s, %s)", (name, email, hashed_password))
        mysql.connection.commit()
        cursor.close()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM customers WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()

        if not user:
            flash('Email is not registered yet', 'danger')
            return redirect(url_for('login'))

        if user and bcrypt.check_password_hash(user[3], password):  # Accessing password using index 3
            login_user(Customer(*user))
            return redirect(url_for('home'))
        else:
            flash('Incorrect email or password', 'danger')
    return render_template('login.html')

#Filtering

# Filtering function with debug prints
def filter_games(games_df, user_selections):
    relevant_categories = set(['Single-player', 'Multi-player', 'PvP', 'Co-op'])
    relevant_genres = set(['Indie', 'Racing', 'Action', 'Adventure', 'Sports', 'RPG'])

    def match_categories(game_categories):
        if pd.isna(game_categories):
            return False
        game_categories_set = set(game_categories.split(','))
        user_categories_set = set(user_selections['categories'])
        
        # The game must include at least one user selected category and should be among the relevant categories
        match = bool(user_categories_set.intersection(game_categories_set)) and bool(game_categories_set.intersection(relevant_categories))
        
        # Ensure all user selected categories are in game categories
        match = match and user_categories_set.issubset(game_categories_set)
        
        # Debug print to verify matching logic
        print(f"Game Categories: {game_categories}, User Categories: {user_selections['categories']}, Match: {match}")
        return match

    def match_genres(game_genres):
        if pd.isna(game_genres):
            return False
        game_genres_set = set(game_genres.split(','))
        user_genres_set = set(user_selections['genres'])
        
        # The game must include at least one user selected genre and should be among the relevant genres
        match = bool(user_genres_set.intersection(game_genres_set)) and bool(game_genres_set.intersection(relevant_genres))
        
        # Ensure all user selected genres are in game genres
        match = match and user_genres_set.issubset(game_genres_set)
        
        # Debug print to verify matching logic
        print(f"Game Genres: {game_genres}, User Genres: {user_selections['genres']}, Match: {match}")
        return match

    def match_payment_type(game_genres, user_payment_types):
        if pd.isna(game_genres):
            return False
        game_genres_set = set(game_genres.split(','))
        is_free_to_play = 'Free to Play' in game_genres_set
        match = ('Free to Play' in user_payment_types and is_free_to_play) or ('Paid Games' in user_payment_types and not is_free_to_play)
        
        # Debug print to verify matching logic
        print(f"Game Genres: {game_genres}, Is Free to Play: {is_free_to_play}, User Payment Types: {user_payment_types}, Match: {match}")
        return match


    def match_platforms(game_platforms, user_platforms):
        if pd.isna(game_platforms):
            return False
        game_platforms_set = set(game_platforms.split(','))
        user_platforms_set = set(user_selections['platforms'])
        
        # The game must support at least one of the user's selected platforms
        match = bool(game_platforms_set.intersection(user_platforms_set))
        
        # Debug print to verify matching logic
        print(f"Game Platforms: {game_platforms}, User Platforms: {user_platforms}, Match: {match}")
        return match

    filtered_games = games_df[
        games_df['categories'].apply(match_categories) &
        games_df['genres'].apply(match_genres) &
        games_df['genres'].apply(lambda x: match_payment_type(x, user_selections['payment'])) &
        games_df['platforms'].apply(lambda x: match_platforms(x, user_selections['platforms']))
    ]
    
    print("Filtered Games: ", filtered_games)  # Debug print to see the filtered games
    return filtered_games

def recommend_top_games(filtered_games, top_n=12):
    return filtered_games.sort_values(by='CompositeRating', ascending=False).head(top_n)

@app.route('/questions')
def questions():
    return render_template('questions.html')

@app.route('/recommend', methods=['POST'])
def recommend():
    categories = request.form.getlist('categories')
    payment = request.form.getlist('payment')
    genres = request.form.getlist('genres')
    platforms = request.form.getlist('platforms')

    user_selections = {
        'categories': categories,
        'payment': payment,
        'genres': genres,
        'platforms': platforms
    }

    print("User Selections: ", user_selections)  # Debug print to see user selections

    filtered_games = filter_games(games_df, user_selections)
    recommended_games = recommend_top_games(filtered_games)

    #print("Recommended Games: ", recommended_games)  # Debug print to see recommended games

    return render_template('suggest.html', games=recommended_games.to_dict(orient='records'))

#Filtering

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        new_name = request.form['name']
        new_email = request.form['email']

        cursor = mysql.connection.cursor()
        cursor.execute("UPDATE customers SET name = %s, email = %s WHERE customerID = %s", (new_name, new_email, current_user.id))
        mysql.connection.commit()
        cursor.close()

        return redirect(url_for('profile'))

    else:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT name, email FROM customers WHERE customerID = %s", (current_user.id,))
        user_data = cursor.fetchone()
        cursor.close()

        if user_data:
            name, email = user_data
            return render_template('profile.html', name=name, email=email, customer=current_user)
        else:
            return redirect(url_for('home'))

@app.route('/games')
def games():
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT * FROM game")
    games = cursor.fetchall()
    cursor.close()
    return render_template('games.html', games=games)

@app.route('/game/<int:game_id>')
def game_detail(game_id):
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT * FROM game WHERE app_id = %s", (game_id,))
    game = cursor.fetchone()
    cursor.close()

    game_details = {
        'id': game[0],
        'app_id': game[1],
        'name': game[2],
        'about_the_game': game[3],
        'required_age': game[4],
        'platforms': game[5],
        'categories': game[6],
        'genres': game[7],
        'price_final_formatted': game[8],
        'ReleaseDate': game[9],
        'Metacritic': game[10],
        'RecommendationCount': game[11],
        'IsFree': game[12],
        'CompositeRating': game[13],
        'header_image': game[14],
        'screenshot1': game[15],
        'screenshot2': game[16],
        'screenshot3': game[17]
    }

    cursor = mysql.connection.cursor()
    query = "SELECT * FROM game_orders WHERE CustomerID = %s AND GameID = %s"
    cursor.execute(query, (current_user.id, game_id))
    in_library = cursor.fetchone() is not None
    cursor.close()

    return render_template('game_details.html', game=game_details, in_library=in_library)

@app.route('/all_games')
def all_games():
    # Pagination logic
    page = request.args.get('page', 1, type=int)
    games_per_page = 20
    offset = (page - 1) * games_per_page

    # Retrieve the top 300 games by composite rating from the database
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT app_id, header_image FROM game ORDER BY CompositeRating DESC LIMIT %s OFFSET %s",
                   (games_per_page, offset))
    games = cursor.fetchall()
    cursor.close()

    # Convert the data into a list of dictionaries
    game_list = [{'app_id': game[0], 'header_image': game[1]} for game in games]

    return render_template('all_games.html', game_list=game_list, page=page, games_per_page=games_per_page)


@app.route('/add_to_library/<int:game_id>/<string:game_name>')
@login_required
def add_to_library(game_id, game_name):
    cursor = mysql.connection.cursor()
    query = "INSERT INTO game_orders (CustomerID, GameID, name) VALUES (%s, %s, %s)"
    try:
        cursor.execute(query, (current_user.id, game_id, game_name))
        mysql.connection.commit()
    except:
        mysql.connection.rollback()
        flash('Error adding game to library', 'danger')
    update_user_profile(current_user.id)
    cursor.close()
    return redirect(url_for('game_detail', game_id=game_id))


@app.route('/remove_from_library/<int:game_id>')
@login_required
def remove_from_library(game_id):
    cursor = mysql.connection.cursor()
    query = "DELETE FROM game_orders WHERE CustomerID = %s AND GameID = %s"
    try:
        cursor.execute(query, (current_user.id, game_id))
        mysql.connection.commit()
    except:
        mysql.connection.rollback()
        flash('Error removing game from library', 'danger')
    cursor.close()
    return redirect(url_for('library'))

@app.route('/library')
@login_required
def library():
    cursor = mysql.connection.cursor()
    query = """
        SELECT game.app_id, game.name, game.header_image 
        FROM game 
        INNER JOIN game_orders ON game.app_id = game_orders.GameID
        WHERE game_orders.CustomerID = %s
    """
    cursor.execute(query, (current_user.id,))
    games = cursor.fetchall()
    cursor.close()

    game_list = [{
        'app_id': game[0],
        'name': game[1],
        'header_image': game[2]
    } for game in games]

    return render_template('library.html', customer=current_user, games=game_list)

@app.route('/add_to_cart/<int:game_id>')
@login_required
def add_to_cart(game_id):
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT name, price_final_formatted, header_image FROM game WHERE app_id = %s", (game_id,))
    game = cursor.fetchone()
    cursor.close()

    if game:
        if 'cart' not in session:
            session['cart'] = {}
        
        # Convert game_id to string to use as a key
        str_game_id = str(game_id)
        
        # Ensure the price is in a proper format
        price = game[1] if game[1] else '0.00'
        
        session['cart'][str_game_id] = {
            'name': game[0],
            'price': price,
            'header_image': game[2]
        }
        
        # Update the session
        session.modified = True
    else:
        flash('Game not found', 'danger')

    return redirect(url_for('view_cart'))


@app.route('/cart')
@login_required
def view_cart():
    if 'cart' not in session or not session['cart']:
        return render_template('cart.html', cart=None)

    cart = session['cart']
    
    total_amount = 0.0
    for game in cart.values():
        if game['price']:
            try:
                total_amount += float(game['price'].replace('$', '').replace(' USD', ''))
            except ValueError:
                flash(f"Invalid price format for game: {game['name']}", 'danger')

    return render_template('cart.html', cart=cart, total_amount=round(total_amount, 2))



@app.route('/remove_from_cart/<int:game_id>')
@login_required
def remove_from_cart(game_id):
    if 'cart' in session and str(game_id) in session['cart']:
        del session['cart'][str(game_id)]
        session.modified = True
    return redirect(url_for('view_cart'))

# Function to log interactions
def log_interaction(user_id, game_id, interaction_type):
    print("Logging interaction:", user_id, game_id, interaction_type)  # Debug statement
    with open('user_interactions.csv', 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([user_id, game_id, interaction_type, datetime.now()])


@app.route('/purchase/<int:game_id>')
@login_required
def purchase(game_id):
    if 'cart' in session and str(game_id) in session['cart']:
        cursor = mysql.connection.cursor()
        try:
            cursor.execute("INSERT INTO game_orders (CustomerID, GameID, name) VALUES (%s, %s, %s)",
                           (current_user.id, game_id, session['cart'][str(game_id)]['name']))
            mysql.connection.commit()
            del session['cart'][str(game_id)]
        except Exception as e:
            print(f"Error: {e}")
            mysql.connection.rollback()
        cursor.close()
    return redirect(url_for('library'))


@app.route('/search')
@login_required
def search():
    query = request.args.get('query', '')
    if not query:
        return redirect(url_for('home'))

    # Query to get the top 300 games based on CompositeRating using DictCursor
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
        SELECT * FROM game 
        ORDER BY CompositeRating DESC 
        LIMIT 800
    """)
    games = cur.fetchall()
    cur.close()

    # Filter games based on the search query
    matching_games = [game for game in games if query.lower() in game['name'].lower()]

    return render_template('search_results.html', query=query, games=matching_games)

@app.route('/payment', methods=['GET', 'POST'])
@login_required
def payment():
    if request.method == 'POST':
        customer_id = current_user.id
        cart = session.get('cart', {})

        cursor = mysql.connection.cursor()
        for game_id, game_details in cart.items():
            cursor.execute(
                "INSERT INTO game_orders (CustomerID, GameID, name) VALUES (%s, %s, %s)",
                (customer_id, game_id, game_details['name'])
            )
        
        mysql.connection.commit()
        update_user_profile(current_user.id)
        cursor.close()

        session.pop('cart', None)
        
        return redirect(url_for('success'))
    
    return render_template('payment.html', customer=current_user)


@app.route('/success')
@login_required
def success():
    return render_template(('success.html'),customer=current_user)

# Updating user profile
def update_user_profile(user_id):
    cursor = mysql.connection.cursor()
    
    # Fetch the feature vectors for all games in the user's library
    cursor.execute("""
        SELECT g.feature_vector
        FROM game_orders o
        JOIN game g ON o.GameID = g.app_id
        WHERE o.CustomerID = %s
    """, (user_id,))
    user_games = cursor.fetchall()
    
    # If no games are found, set user_profile to None
    if not user_games:
        user_profile = None
    else:
        # Calculate the mean of feature vectors
        feature_vectors = []
        for game in user_games:
            try:
                vector = np.array(eval(game[0]))  # Convert string to numpy array
                feature_vectors.append(vector)
            except Exception as e:
                print(f"Error parsing feature vector {game[0]}: {e}")
        
        if feature_vectors:
            user_profile = np.mean(feature_vectors, axis=0).tolist()
        else:
            user_profile = None
    
    # Update the user_profile in the customers table
    try:
        cursor.execute("UPDATE customers SET user_profile = %s WHERE customerID = %s", (str(user_profile), user_id))
        mysql.connection.commit()
    except Exception as e:
        print(f"Error updating user profile: {e}")
        mysql.connection.rollback()
    finally:
        cursor.close()

@app.route('/recommendations')
@login_required
def recommendations():
    user_profile = eval(current_user.user_profile) if current_user.user_profile else []
    
    if not user_profile:
        flash('No user profile available. Please add games to your library to generate recommendations.', 'danger')
        return redirect(url_for('home'))
    
    recommended_game_ids = get_recommendations(user_profile, current_user.id)
    
    cursor = mysql.connection.cursor()
    format_strings = ','.join(['%s'] * len(recommended_game_ids))
    cursor.execute(f"SELECT * FROM game WHERE app_id IN ({format_strings})", tuple(recommended_game_ids))
    recommended_games = cursor.fetchall()
    cursor.close()
    
    return render_template('home.html', recommended_games=recommended_games)

def get_recommendations(user_profile, user_id, top_n=7):
    cursor = mysql.connection.cursor()
    
    # Fetch games in the user's library
    cursor.execute("""
        SELECT g.app_id
        FROM game_orders o
        JOIN game g ON o.GameID = g.app_id
        WHERE o.CustomerID = %s
    """, (user_id,))
    user_game_ids = {game[0] for game in cursor.fetchall()}
    
    # Fetch all games with their feature vectors
    cursor.execute("SELECT app_id, feature_vector FROM game ORDER BY CompositeRating DESC LIMIT 800")
    games = cursor.fetchall()
    cursor.close()
    
    game_ids = [game[0] for game in games if game[0] not in user_game_ids]
    game_vectors = [np.array(eval(game[1])) for game in games if game[0] not in user_game_ids]
    
    # Calculate similarity scores
    similarity_scores = cosine_similarity([user_profile], game_vectors).flatten()
    
    # Get top N recommendations
    top_indices = similarity_scores.argsort()[-top_n:][::-1]
    recommended_game_ids = [game_ids[i] for i in top_indices]
    
    return recommended_game_ids

if __name__ == '__main__':
    app.run(debug=True)
