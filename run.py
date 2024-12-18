from app import create_app
from app.models import db, BlogPost, User, Comment, ECommercePost, Cart
from flask import render_template, redirect, url_for, flash, abort
from flask_login import current_user, login_user, logout_user, login_required
from app.forms import RegisterForm, LoginForm, CreatePostForm, CommentForm, CreateECommerceForm
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date
from functools import wraps
from sqlalchemy import func

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

@app.route('/register', methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        if db.session.execute(db.select(User).where(User.email == form.email.data)).scalar():
            flash("You've already signed up with that email, log in instead!")
            return redirect(url_for('login'))

        hashed_password = generate_password_hash(form.password.data, method='pbkdf2:sha256', salt_length=8)
        new_user = User(email=form.email.data, name=form.name.data, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('get_all_posts'))

    return render_template("register.html", form=form, current_user=current_user)

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

if __name__ == "__main__":
    app.run(debug=True)
