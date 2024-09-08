import os
import sqlalchemy as sa
import dnevnik2
from flask import (Flask, request,
                   render_template, redirect, flash, abort, url_for)
from wtforms.form import Form
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, current_user, coo

app = Flask(__name__, template_folder='templates')
app.secret_key = b'_5#y2L"F4Q8z\n\xec]/'

file_path = os.path.abspath(os.getcwd()) + "/db_file/dnevnik.db"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + file_path

login_manager = LoginManager()
login_manager.init_app(app)

db = SQLAlchemy(app)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(64), unique=True)
    password = db.Column(db.String(128))


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect('index')
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        dnevnik = dnevnik2.Dnevnik2.make_from_login_by_email(email, password)
        print(dnevnik.session.cookies)

        user = db.session.scalar(
            sa.select(User).where(User.email == email, User.password == password))
        login_user(user, remember=True)
        return redirect('index')

    return render_template('login.html')


@app.route('/index', methods=['GET'])
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    return 'SUCCESS!'


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run()
