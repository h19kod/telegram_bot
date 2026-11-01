from django.urls import path

from apps.accounts import views

urlpatterns = [
    path("register", views.RegisterView.as_view()),
    path("login", views.LoginView.as_view()),
    path("refresh", views.RefreshView.as_view()),
    path("logout", views.LogoutView.as_view()),
    path("me", views.MeView.as_view()),
    path("me/memberships", views.MyMembershipsView.as_view()),
    path("password/change", views.PasswordChangeView.as_view()),
    path("password/reset", views.PasswordResetView.as_view()),
    path("password/reset/confirm", views.PasswordResetConfirmView.as_view()),
    path("2fa/setup", views.TotpSetupView.as_view()),
    path("2fa/enable", views.TotpEnableView.as_view()),
    path("2fa/disable", views.TotpDisableView.as_view()),
    path("telegram/link-code", views.TelegramLinkCodeView.as_view()),
    path("telegram", views.TelegramLinkCodeView.as_view()),
    path("ws-ticket", views.WsTicketView.as_view()),
    path("invitations/<str:token>/accept", views.AcceptInvitationView.as_view()),
]
