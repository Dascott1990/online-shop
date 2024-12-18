from app import create_app
from app.models import db, BlogPost, User, Comment, ECommercePost, Cart
from flask import render_template, redirect, url_for, flash, abort, session
from flask_login import current_user, login_user, logout_user, login_required
from app.forms import RegisterForm, LoginForm, CreatePostForm, CommentForm, CreateECommerceForm, VerificationForm
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date
from functools import wraps
from sqlalchemy import func
import random
import string
import smtplib
import ssl
import logging
import os
# Import payment utilities
from payment import create_stripe_checkout_session, create_crypto_payment

# Initialize Flask application
app = create_app()

# Create database tables
with app.app_context():
    db.create_all()

# Admin-only route decorator
def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.id != 1:
            return abort(403)
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def get_all_posts():
    posts = db.session.execute(db.select(BlogPost)).scalars().all()
    products = db.session.execute(db.select(ECommercePost)).scalars().all()

    # Get cart item count for the current user
    if current_user.is_authenticated:
        cart_item_count = db.session.execute(
            db.select(func.count(Cart.id)).where(Cart.user_id == current_user.id)
        ).scalar()
    else:
        cart_item_count = 0

    return render_template("index.html", all_posts=posts, all_products=products, current_user=current_user, cart_item_count=cart_item_count)

# Helper function to generate a 6-digit verification code
def generate_verification_code():
    return ''.join(random.choices(string.digits, k=6))

# Helper function to send verification email
def send_verification_email(user_email, verification_code):
    email_message = f"""
    Subject: Email Verification Code

    We sent an email with a verification code to {user_email}.
    Enter it below to confirm your email.

    Verification code: {verification_code}
    """
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as connection:
            connection.login(os.environ['EMAIL_ADDRESS'], os.environ['EMAIL_PASSWORD'])
            connection.sendmail(os.environ['EMAIL_ADDRESS'], user_email, email_message)
        print("Verification email sent successfully!")
    except Exception as e:
        logging.error(f"Error sending verification email: {e}")

@app.route('/register', methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        user = db.session.execute(db.select(User).where(User.email == form.email.data)).scalar()
        if user:
            flash("You've already signed up with that email, log in instead!")
            return redirect(url_for('login'))

        # Store user details in the session temporarily
        session['user_email'] = form.email.data
        session['user_password'] = form.password.data
        session['user_name'] = form.name.data

        # Generate and store the verification code
        verification_code = generate_verification_code()
        session['verification_code'] = verification_code

        # Send verification email
        send_verification_email(form.email.data, verification_code)
        return redirect(url_for('verify_email'))
    return render_template("register.html", form=form, current_user=current_user)

@app.route('/verify', methods=["GET", "POST"])
def verify_email():
    form = VerificationForm()
    if form.validate_on_submit():
        if form.verification_code.data == session.get('verification_code'):
            flash("Email verified successfully!")

            # Retrieve user details and save to the database
            email = session.pop('user_email')
            password = generate_password_hash(session.pop('user_password'))
            name = session.pop('user_name')

            new_user = User(email=email, name=name, password=password)
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)

            return redirect(url_for('get_all_posts'))
        else:
            flash("Invalid verification code. Please try again.")
    return render_template("verify.html", form=form)

@app.route('/resend-verification-code', methods=["GET"])
def resend_verification_code():
    if 'user_email' in session:
        verification_code = generate_verification_code()
        session['verification_code'] = verification_code
        send_verification_email(session['user_email'], verification_code)
        flash("A new verification code has been sent to your email.")
        return redirect(url_for('verify_email'))
    flash("No email found in session.")
    return redirect(url_for('register'))

@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.execute(db.select(User).where(User.email == form.email.data)).scalar()
        if not user or not check_password_hash(user.password, form.password.data):
            flash("Incorrect email or password. Please try again.")
            return redirect(url_for('login'))
        login_user(user)
        return redirect(url_for('get_all_posts'))
    return render_template("login.html", form=form, current_user=current_user)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))

@app.route('/post/<int:post_id>', methods=["GET", "POST"])
def show_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    form = CommentForm()
    if form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("You need to log in or register to comment.")
            return redirect(url_for("login"))
        new_comment = Comment(
            text=form.comment_text.data,
            comment_author=current_user,
            parent_post=post
        )
        db.session.add(new_comment)
        db.session.commit()
    return render_template("post.html", post=post, form=form, current_user=current_user)

@app.route('/new-product', methods=["GET", "POST"])
@admin_only
def add_new_product():
    form = CreateECommerceForm()
    if form.validate_on_submit():
        new_product = ECommercePost(
            title=form.title.data,
            description=form.description.data,
            price=form.price.data,
            img_url=form.img_url.data
        )
        db.session.add(new_product)
        db.session.commit()
        flash("New product added successfully!")
        return redirect(url_for('shop'))
    return render_template("make-product.html", form=form, current_user=current_user)

@app.route('/new-post', methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for('get_all_posts'))
    return render_template("make-post.html", form=form, current_user=current_user)

@app.route('/edit-post/<int:post_id>', methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    form = CreatePostForm(obj=post)
    if form.validate_on_submit():
        post.title = form.title.data
        post.subtitle = form.subtitle.data
        post.img_url = form.img_url.data
        post.body = form.body.data
        db.session.commit()
        return redirect(url_for('show_post', post_id=post.id))
    return render_template("make-post.html", form=form, is_edit=True, current_user=current_user)

@app.route('/delete/<int:post_id>')
@admin_only
def delete_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    db.session.delete(post)
    db.session.commit()
    return redirect(url_for('get_all_posts'))

@app.route('/about')
def about():
    return render_template("about.html", current_user=current_user)

@app.route('/contact')
def contact():
    return render_template("contact.html", current_user=current_user)

@app.route('/shop', methods=["GET"])
def shop():
    items = db.session.execute(db.select(ECommercePost)).scalars().all()
    return render_template("shop.html", all_products=items, current_user=current_user)

@app.route('/cart', methods=["GET", "POST"])
@login_required
def view_cart():
    cart_items = db.session.execute(
        db.select(Cart).where(Cart.user_id == current_user.id)
    ).scalars().all()
    total_price = sum(item.item.price * item.quantity for item in cart_items)
    return render_template("cart.html", cart_items=cart_items, total_price=total_price, current_user=current_user)

@app.route('/add-to-cart/<int:item_id>', methods=["POST"])
@login_required
def add_to_cart(item_id):
    cart_item = db.session.execute(
        db.select(Cart).where(Cart.user_id == current_user.id, Cart.item_id == item_id)
    ).scalar()
    if cart_item:
        cart_item.quantity += 1
    else:
        new_cart_item = Cart(user_id=current_user.id, item_id=item_id, quantity=1)
        db.session.add(new_cart_item)
    db.session.commit()
    flash("Item added to cart!")
    return redirect(url_for('shop'))


@app.route('/remove-from-cart/<int:cart_id>', methods=["POST"])
@login_required
def remove_from_cart(cart_id):
    cart_item = db.get_or_404(Cart, cart_id)
    if cart_item.user_id != current_user.id:
        abort(403)
    db.session.delete(cart_item)
    db.session.commit()
    flash("Item removed from cart!")
    return redirect(url_for('view_cart'))

@app.route('/clear-cart', methods=["POST"])
@login_required
def clear_cart():
    db.session.query(Cart).filter_by(user_id=current_user.id).delete()
    db.session.commit()
    flash("Cart cleared!")
    return redirect(url_for('view_cart'))

# New route to view individual product details
@app.route('/product/<int:product_id>', methods=["GET"])
def show_product(product_id):
    product = db.get_or_404(ECommercePost, product_id)  # Fetch the product by ID
    return render_template("product.html", product=product, current_user=current_user)



@app.route('/checkout/stripe', methods=["POST"])
@login_required
def stripe_checkout():
    cart_items = [
        {
            'title': item.item.title,
            'price': item.item.price,
            'quantity': item.quantity,
        }
        for item in db.session.query(Cart).filter_by(user_id=current_user.id).all()
    ]
    success_url = url_for('payment_success', _external=True)
    cancel_url = url_for('payment_cancel', _external=True)

    stripe_url = create_stripe_checkout_session(cart_items, success_url, cancel_url)
    if stripe_url:
        return redirect(stripe_url)
    flash("Failed to create Stripe checkout session.")
    return redirect(url_for('view_cart'))

@app.route('/checkout/crypto', methods=["POST"])
@login_required
def crypto_checkout():
    cart_items = [
        {
            'title': item.item.title,
            'price': item.item.price,
            'quantity': item.quantity,
        }
        for item in db.session.query(Cart).filter_by(user_id=current_user.id).all()
    ]

    crypto_payment = create_crypto_payment(cart_items, user_wallet_address="user_wallet_address_here")
    if crypto_payment:
        return render_template("crypto_payment.html", payment_info=crypto_payment)
    flash("Failed to generate crypto payment.")
    return redirect(url_for('view_cart'))

@app.route('/payment-success')
def payment_success():
    flash("Payment was successful!")
    return redirect(url_for('view_cart'))

@app.route('/payment-cancel')
def payment_cancel():
    flash("Payment was cancelled.")
    return redirect(url_for('view_cart'))

if __name__ == "__main__":
    app.run(debug=True)
