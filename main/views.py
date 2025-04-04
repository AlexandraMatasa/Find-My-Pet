from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from .forms import RegisterForm, ConfirmPasswordForm, EditProfileForm, LostPostForm, FoundPostForm
from django.contrib.auth import login, logout, authenticate

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.contrib import messages
from django.views.generic.edit import UpdateView

from .models import User, LostPost, FoundPost, PetImage
from django.urls import reverse_lazy
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.contrib.auth.decorators import user_passes_test
from django.contrib.messages import get_messages
import matplotlib.pyplot as plt
import io
import base64
from django.shortcuts import render
from django.db import models
from collections import Counter


def home(request):
    if request.user.is_authenticated:
        user = request.user
        if isinstance(user, User) and user.is_superadmin:
            return redirect('/admin')
        elif user.is_admin:
            return redirect('/admin')
    post_type = request.GET.get('post_type', 'lost')
    search_query = request.GET.get('search', '')
    filter_criteria = request.GET.get('filter', '')

    if post_type == 'lost':
        posts = LostPost.objects.filter(is_archived=False).prefetch_related('images').order_by('-created_at')
    elif post_type == 'found':
        posts = FoundPost.objects.filter(is_archived=False).prefetch_related('images').order_by('-created_at')
    else:
        posts = []

    if search_query:
        posts = posts.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(area__icontains=search_query) |
            Q(pet_name__icontains=search_query)
        )

    if filter_criteria:
        if filter_criteria == 'cat':
            posts = posts.filter(pet_type='cat')
        elif filter_criteria == 'dog':
            posts = posts.filter(pet_type='dog')
        elif filter_criteria == 'other':
            posts = posts.filter(pet_type='other')

    return render(request, 'main/show_posts.html', {
        'posts': posts,
        'post_type': post_type,
        'page_title': 'Home Page',
        'search_query': search_query,
        'filter_criteria': filter_criteria,
    })


@login_required
def my_posts(request):
    post_type = request.GET.get('post_type', 'lost')

    if post_type == 'lost':
        posts = LostPost.objects.filter(user=request.user, is_archived=False).prefetch_related('images').order_by(
            '-created_at')
    elif post_type == 'found':
        posts = FoundPost.objects.filter(user=request.user, is_archived=False).prefetch_related('images').order_by(
            '-created_at')
    else:
        posts = []

    return render(request, 'main/show_posts.html', {
        'posts': posts,
        'post_type': post_type,
        'page_title': 'My Posts',
    })


@login_required
def my_archive(request):
    post_type = request.GET.get('post_type', 'lost')

    if post_type == 'lost':
        posts = LostPost.objects.filter(user=request.user, is_archived=True).prefetch_related('images').order_by(
            '-created_at')
    elif post_type == 'found':
        posts = FoundPost.objects.filter(user=request.user, is_archived=True).prefetch_related('images').order_by(
            '-created_at')
    else:
        posts = []

    return render(request, 'main/show_posts.html', {
        'posts': posts,
        'post_type': post_type,
        'page_title': 'My Archive',
    })


@login_required(login_url='/login')
def create_post(request, post_type):
    form_class = LostPostForm if post_type == 'lost' else FoundPostForm

    if request.method == 'POST':
        form = form_class(request.POST, user=request.user)
        if form.is_valid():
            post = form.save(commit=False)
            post.user = request.user
            post.save()

            images = request.FILES.getlist('images')
            for image in images:
                PetImage.objects.create(
                    content_type=ContentType.objects.get_for_model(post.__class__),
                    object_id=post.id,
                    image=image
                )

            return redirect('/home')
    else:
        form = form_class(user=request.user)

    return render(request, 'main/create_post.html', {
        'form': form,
        'post_type': post_type.capitalize(),
        'is_edit': False,
        'is_view': False,
    })


def sign_up(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('/home')
    else:
        form = RegisterForm()

    return render(request, 'registration/sign_up.html', {"form": form})


def log_out(request):
    logout(request)
    return redirect('/login')


def about(request):
    return render(request, 'about.html')


class DeleteAccountView(LoginRequiredMixin, TemplateView):
    template_name = 'delete_account.html'

    def get(self, request, *args, **kwargs):
        form = ConfirmPasswordForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request, *args, **kwargs):
        form = ConfirmPasswordForm(request.POST)
        if form.is_valid():
            password = form.cleaned_data['password']
            user = authenticate(username=request.user.username, password=password)
            if user:
                user.delete()
                return redirect('home')
            else:
                messages.error(request, "Incorrect password. Please try again.")
        else:
            messages.error(request, "Please confirm your password.")
        return render(request, self.template_name, {'form': form})


class EditProfileView(UpdateView):
    model = User
    form_class = EditProfileForm
    template_name = 'edit_profile.html'
    success_url = reverse_lazy('home')

    def get_object(self):
        return self.request.user


@login_required
def edit_post(request, post_id):
    post_type = request.GET.get('post_type', 'lost')
    post_model = LostPost if post_type == 'lost' else FoundPost
    post = get_object_or_404(post_model, id=post_id, user=request.user)

    form_class = LostPostForm if post_type == 'lost' else FoundPostForm
    form = form_class(instance=post, data=request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            post = form.save()

            removed_image_ids = request.POST.get('removed_existing_images', '')
            if removed_image_ids:
                removed_image_ids = [int(image_id) for image_id in removed_image_ids.split(',')]
                PetImage.objects.filter(id__in=removed_image_ids).delete()

            images = request.FILES.getlist('images')
            for image in images:
                PetImage.objects.create(
                    content_type=ContentType.objects.get_for_model(post.__class__),
                    object_id=post.id,
                    image=image
                )

            messages.success(request, "Post updated successfully.")
        return redirect(f'/my_posts/?post_type={post_type}')

    existing_images = post.images.all()
    return render(request, 'main/create_post.html', {
        'form': form,
        'post_type': post_type.capitalize(),
        'is_edit': True,
        'is_view': False,
        'existing_images': existing_images,
    })


@login_required
def delete_post(request, post_id):
    post_type = request.GET.get('post_type')
    if post_type == 'lost':
        post_model = LostPost
    elif post_type == 'found':
        post_model = FoundPost
    else:
        messages.error(request, "Invalid post type.")
        return redirect('my_posts')

    post = get_object_or_404(post_model, id=post_id, user=request.user)

    if request.method == 'POST':
        post.delete()
        messages.success(request, "Post deleted successfully.")
        return redirect(f'/my_posts/?post_type={post_type}')

    messages.error(request, "Invalid request method.")
    return redirect('my_posts')


@login_required
def archive_post(request, post_id):
    post_type = request.GET.get('post_type')

    if post_type == 'lost':
        post_model = LostPost
    elif post_type == 'found':
        post_model = FoundPost
    else:
        messages.error(request, "Invalid post type.")
        return redirect('/manage_posts/' if request.user.is_superadmin or request.user.is_admin else '/my_posts/')

    if request.user.is_superadmin or request.user.is_admin:
        post = get_object_or_404(post_model, id=post_id)
    else:
        post = get_object_or_404(post_model, id=post_id, user=request.user)

    post.is_archived = True
    post.save()

    messages.success(request, "Post archived successfully.")

    if request.user.is_superadmin or request.user.is_admin:
        return redirect(f'/manage_posts/?post_type={post_type}&archived=0')
    else:
        return redirect(f'/my_posts/?post_type={post_type}')


@login_required
def unarchive_post(request, post_id):
    post_type = request.GET.get('post_type')

    if post_type == 'lost':
        post_model = LostPost
    elif post_type == 'found':
        post_model = FoundPost
    else:
        messages.error(request, "Invalid post type.")
        return redirect('/manage_posts/' if request.user.is_superadmin or request.user.is_admin else '/my_archive/')

    if request.user.is_superadmin or request.user.is_admin:
        post = get_object_or_404(post_model, id=post_id)
    else:
        post = get_object_or_404(post_model, id=post_id, user=request.user)

    post.is_archived = False
    post.save()

    messages.success(request, "Post unarchived successfully.")

    if request.user.is_superadmin or request.user.is_admin:
        return redirect(f'/manage_posts/?post_type={post_type}&archived=1')
    else:
        return redirect(f'/my_archive/?post_type={post_type}')


def post_detail(request, post_id):
    post_type = request.GET.get('post_type', 'lost')
    post_model = LostPost if post_type == 'lost' else FoundPost
    post = get_object_or_404(post_model, id=post_id)

    form_class = LostPostForm if post_type == 'lost' else FoundPostForm
    form = form_class(instance=post)

    if 'reward' in form.fields:
        reward_value = f"{form.instance.reward} $" if form.instance.reward else "No reward"
        form.fields['reward'].widget.attrs['placeholder'] = reward_value
        form.fields['reward'].help_text = ''

    for field_name in ['email', 'phone_number']:
        if field_name in form.fields:
            form.fields[field_name].widget.attrs.update({
                'class': 'form-control highlight-field',
            })

    for field in form.fields.values():
        field.required = False
        field.disabled = True
    return render(request, 'main/create_post.html', {
        'form': form,
        'post_type': post_type.capitalize(),
        'is_edit': False,
        'is_view': True,
        'highlight_fields': {
            'email': form.instance.email,
            'phone_number': form.instance.phone_number,
        }
    })


def is_admin_or_superadmin(user):
    return user.is_authenticated and (user.is_admin or user.is_superadmin)

@user_passes_test(is_admin_or_superadmin)
def manage_posts(request):
    if request.user.is_superadmin or request.user.is_admin:
        storage = get_messages(request)
        list(storage)

    post_type = request.GET.get('post_type', 'lost')
    is_archived = request.GET.get('archived', '0') == '1'  # 0 = Active, 1 = Archived
    is_superadmin = request.user.is_superadmin

    if post_type == 'lost':
        posts = LostPost.objects.filter(is_archived=is_archived).order_by('-created_at')
    elif post_type == 'found':
        posts = FoundPost.objects.filter(is_archived=is_archived).order_by('-created_at')
    else:
        posts = []

    return render(request, 'manage_posts.html', {
        'posts': posts,
        'post_type': post_type,
        'is_archived': is_archived,
        'is_superadmin': is_superadmin,
    })


@login_required
def view_statistics(request):
    if not (request.user.is_superadmin or request.user.is_admin):
        return redirect('home')

    lost_posts_count = LostPost.objects.filter(is_archived=False).count()
    found_posts_count = FoundPost.objects.filter(is_archived=False).count()

    daily_lost = (
        LostPost.objects.extra(select={'day': "DATE(created_at)"}).values('day')
        .annotate(count=models.Count('id')).order_by('day')
    )
    daily_found = (
        FoundPost.objects.extra(select={'day': "DATE(created_at)"}).values('day')
        .annotate(count=models.Count('id')).order_by('day')
    )

    lost_species_distribution = (
        LostPost.objects.values('pet_type')
        .annotate(count=models.Count('id'))
        .order_by('pet_type')
    )

    found_species_distribution = (
        FoundPost.objects.values('pet_type')
        .annotate(count=models.Count('id'))
        .order_by('pet_type')
    )

    species_counter = Counter()
    for entry in lost_species_distribution:
        species_counter[entry['pet_type']] += entry['count']
    for entry in found_species_distribution:
        species_counter[entry['pet_type']] += entry['count']

    species_labels = list(species_counter.keys())
    species_counts = list(species_counter.values())

    user_activities = Counter()
    for entry in daily_lost:
        user_activities[entry['day']] += entry['count']
    for entry in daily_found:
        user_activities[entry['day']] += entry['count']

    activity_dates = sorted(user_activities.keys())
    activity_counts = [user_activities[date] for date in activity_dates]

    def generate_chart(x, y, title, chart_type="line", color="blue"):
        plt.figure(figsize=(8, 4))
        if chart_type == "bar":
            plt.bar(x, y, color=color)
            plt.title(title)
            plt.xlabel('Date')
            plt.ylabel('Count')
        elif chart_type == "line":
            plt.plot(x, y, marker='o', color=color, label='User Activity')
            plt.title(title)
            plt.xlabel('Date')
            plt.ylabel('Number of Posts')
            plt.legend()
        elif chart_type == "pie":
            plt.pie(y, labels=x, autopct='%1.1f%%', startangle=140)
            plt.title(title)
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png')
        buffer.seek(0)
        image_png = buffer.getvalue()
        buffer.close()
        return base64.b64encode(image_png).decode('utf-8')

    lost_daily_chart = generate_chart(
        [entry['day'] for entry in daily_lost],
        [entry['count'] for entry in daily_lost],
        "Lost Posts Over Time",
        "bar"
    )
    found_daily_chart = generate_chart(
        [entry['day'] for entry in daily_found],
        [entry['count'] for entry in daily_found],
        "Found Posts Over Time",
        "bar",
        color="green"
    )
    user_activity_chart = generate_chart(
        activity_dates,
        activity_counts,
        "User Activities Over Time",
        "line",
        color="orange"
    )
    species_chart = generate_chart(
        species_labels,
        species_counts,
        "Species Distribution",
        "pie"
    )

    return render(request, 'view_statistics.html', {
        'lost_posts_count': lost_posts_count,
        'found_posts_count': found_posts_count,
        'lost_daily_chart': lost_daily_chart,
        'found_daily_chart': found_daily_chart,
        'user_activity_chart': user_activity_chart,
        'species_chart': species_chart,
    })
