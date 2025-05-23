from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import login, authenticate, logout
from django.contrib import messages

# Home page view
def home(request):
    return render(request, 'device/home.html')

# User registration
def user_register(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
        elif User.objects.filter(username=username).exists():
            messages.error(request, "Username already taken.")
        else:
            user = User.objects.create_user(username=username, email=email, password=password)
            login(request, user)
            messages.success(request,"Account created successfully")
            return redirect('device_list')

    return render(request, 'user/register.html')

# Login user
def user_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            messages.success(request, "Logged in successfully")
            return redirect('device_list')
        else:
            messages.error(request, "Invalid credentials.")

    return render(request, 'user/login.html')

# Logout user
def user_logout(request):
    logout(request)
    return redirect('login')
