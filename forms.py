from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, TextAreaField, SubmitField, BooleanField, IntegerField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError, Optional, NumberRange
from wtforms.widgets import HiddenInput
from models import User


def strip_value(value):
    return value.strip() if isinstance(value, str) else value


def normalize_email(value):
    return value.strip().lower() if isinstance(value, str) else value

class LoginForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired()], filters=[strip_value])
    password = PasswordField('密码', validators=[DataRequired()])
    remember_me = BooleanField('记住我')
    submit = SubmitField('登录')

class RegisterForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired(), Length(min=3, max=20)], filters=[strip_value])
    email = StringField('电子邮箱', validators=[DataRequired(), Email()], filters=[normalize_email])
    password = PasswordField('密码', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('确认密码', validators=[DataRequired(), EqualTo('password', message='两次输入的密码不一致')])
    submit = SubmitField('注册')

    def validate_username(self, username):
        user = User.get_by_username(username.data)
        if user is not None:
            raise ValidationError('该用户名已被使用')

    def validate_email(self, email):
        conn = User.get_by_email(email.data)
        if conn is not None:
            raise ValidationError('该邮箱已被注册')

class PostForm(FlaskForm):
    title = StringField('标题', validators=[DataRequired(), Length(min=3, max=100)], filters=[strip_value])
    content = TextAreaField('内容', validators=[DataRequired(), Length(min=10, max=1000)], filters=[strip_value])
    submit = SubmitField('发布')

class CommentForm(FlaskForm):
    content = TextAreaField('评论', validators=[DataRequired(), Length(min=2, max=500)], filters=[strip_value])
    parent_id = IntegerField('回复评论ID', validators=[Optional(), NumberRange(min=1)], widget=HiddenInput())
    submit = SubmitField('发表评论')

class EditProfileForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired(), Length(min=3, max=20)], filters=[strip_value])
    email = StringField('电子邮箱', validators=[DataRequired(), Email()], filters=[normalize_email])
    current_password = PasswordField('当前密码', validators=[Optional()])
    password = PasswordField('新密码', validators=[Optional(), Length(min=6)])
    password2 = PasswordField('确认密码', validators=[EqualTo('password', message='两次输入的密码不一致')])
    submit = SubmitField('保存修改')

    def __init__(self, original_username, original_email, *args, **kwargs):
        super(EditProfileForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.original_email = normalize_email(original_email)

    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.get_by_username(username.data)
            if user is not None:
                raise ValidationError('该用户名已被使用')
    
    def validate_email(self, email):
        if email.data != self.original_email:
            user = User.get_by_email(email.data)
            if user is not None:
                raise ValidationError('该邮箱已被注册')

class AdminEditProfileForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired(), Length(min=3, max=20)], filters=[strip_value])
    email = StringField('电子邮箱', validators=[DataRequired(), Email()], filters=[normalize_email])
    password = PasswordField('新密码 (留空则保持不变)', validators=[Optional(), Length(min=6)])
    password2 = PasswordField('确认新密码', validators=[EqualTo('password', message='两次输入的密码不一致')])
    is_admin = BooleanField('管理员权限')
    is_sub_admin = BooleanField('子管理员权限')
    is_banned = BooleanField('封禁用户')
    banned_reason = StringField('封禁原因', validators=[Optional(), Length(max=200)])
    submit = SubmitField('保存修改')

    def __init__(self, original_username, original_email, *args, **kwargs):
        super(AdminEditProfileForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.original_email = normalize_email(original_email)

    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.get_by_username(username.data)
            if user is not None:
                raise ValidationError('该用户名已被使用')
    
    def validate_email(self, email):
        if email.data != self.original_email:
            user = User.get_by_email(email.data)
            if user is not None:
                raise ValidationError('该邮箱已被注册')
    
    def validate_is_admin(self, is_admin):
        if is_admin.data and self.is_sub_admin.data:
            raise ValidationError('用户不能同时是管理员和子管理员')

    def validate_is_banned(self, is_banned):
        if is_banned.data and not strip_value(self.banned_reason.data or ''):
            raise ValidationError('封禁用户时必须填写封禁原因')

class BanUserForm(FlaskForm):
    reason = TextAreaField('封禁原因', validators=[DataRequired(), Length(min=5, max=200)])
    submit = SubmitField('确认封禁')

