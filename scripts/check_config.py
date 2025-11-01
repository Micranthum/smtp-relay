#!/usr/bin/env python3
"""
Script para verificar la configuración de cifrado del SMTP Relay
"""
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from config import Config

def check_config():
    """Verificar configuración actual"""
    print("=" * 70)
    print("SMTP Relay - Verificación de Configuración")
    print("=" * 70)
    print()
    
    # Cargar configuración
    print("📋 Configuración del Servidor SMTP:")
    print(f"   Host: {Config.SMTP_RELAY_HOST}")
    print(f"   Puerto: {Config.SMTP_RELAY_PORT}")
    print(f"   Modo de Cifrado: {Config.SMTP_ENCRYPTION_MODE}")
    print(f"   TLS Habilitado: {Config.SMTP_RELAY_USE_TLS}")
    print()
    
    # Información de cifrado
    print("🔐 Configuración de Cifrado:")
    if Config.SMTP_ENCRYPTION_MODE == 'SSL':
        print("   ✅ Modo SSL: Conexión cifrada desde el inicio (TLS implícito)")
        print(f"   📝 Puerto típico: 465 (actual: {Config.SMTP_RELAY_PORT})")
        print("   📌 Compatible con: Programas antiguos, Contpaq legacy")
    elif Config.SMTP_ENCRYPTION_MODE == 'STARTTLS':
        print("   ✅ Modo STARTTLS: Conexión inicia sin cifrar, se actualiza a TLS")
        print(f"   📝 Puerto típico: 587 (actual: {Config.SMTP_RELAY_PORT})")
        print("   📌 Compatible con: Clientes modernos")
    elif Config.SMTP_ENCRYPTION_MODE == 'NONE':
        print("   ⚠️  Modo NONE: Sin cifrado - SOLO PARA DESARROLLO")
        print("   🚨 NO USAR EN PRODUCCIÓN")
    else:
        print(f"   ❌ Modo desconocido: {Config.SMTP_ENCRYPTION_MODE}")
    print()
    
    # Certificados TLS
    print("📜 Certificados TLS:")
    if Config.SMTP_ENCRYPTION_MODE in ['SSL', 'STARTTLS']:
        if Config.SMTP_ENCRYPTION_MODE == 'SSL' or Config.SMTP_RELAY_USE_TLS:
            if Config.TLS_CERT_FILE and Config.TLS_KEY_FILE:
                print(f"   Certificado: {Config.TLS_CERT_FILE}")
                print(f"   Clave: {Config.TLS_KEY_FILE}")
                
                # Verificar que existan
                from pathlib import Path
                cert_exists = Path(Config.TLS_CERT_FILE).exists()
                key_exists = Path(Config.TLS_KEY_FILE).exists()
                
                if cert_exists and key_exists:
                    print("   ✅ Archivos de certificado encontrados")
                else:
                    if not cert_exists:
                        print(f"   ❌ Certificado no encontrado: {Config.TLS_CERT_FILE}")
                    if not key_exists:
                        print(f"   ❌ Clave no encontrada: {Config.TLS_KEY_FILE}")
            else:
                print("   ❌ Certificados TLS no configurados")
                print("   ⚠️  Requeridos para este modo de cifrado")
        else:
            print("   ⚠️  TLS deshabilitado en modo STARTTLS")
    else:
        print("   ℹ️  No requeridos para modo NONE")
    print()
    
    # Seguridad
    print("🔒 Configuración de Seguridad:")
    print(f"   IPs Permitidas: {Config.ALLOWED_IPS}")
    if Config.ALLOWED_IPS == '*':
        print("   ⚠️  ADVERTENCIA: Todas las IPs están permitidas")
        if Config.ENVIRONMENT == 'production':
            print("   🚨 Considerar restringir en producción")
    print(f"   Remitentes Permitidos: {Config.ALLOWED_SENDERS}")
    print()
    
    # Autenticación
    print("🔑 Autenticación:")
    print(f"   Usuario SMTP: {Config.SMTP_RELAY_USERNAME}")
    print(f"   Password configurado: {'Sí' if Config.SMTP_RELAY_PASSWORD else 'No'}")
    print()
    
    # Microsoft 365
    print("☁️  Microsoft 365:")
    print(f"   Email: {Config.MS365_EMAIL_ADDRESS}")
    print(f"   Tenant ID: {Config.MS365_TENANT_ID[:20]}..." if Config.MS365_TENANT_ID else "   Tenant ID: No configurado")
    print(f"   Client ID configurado: {'Sí' if Config.MS365_CLIENT_ID else 'No'}")
    print(f"   Secret configurado: {'Sí' if Config.MS365_CLIENT_SECRET else 'No'}")
    print()
    
    # Otros
    print("⚙️  Otros:")
    print(f"   Entorno: {Config.ENVIRONMENT}")
    print(f"   Nivel de Log: {Config.LOG_LEVEL}")
    print(f"   Límite de Tasa: {Config.RATE_LIMIT_PER_MINUTE} emails/minuto")
    print()
    
    # Validar
    print("🔍 Validando configuración...")
    try:
        Config.validate()
        print("   ✅ Configuración válida")
        print()
        print("=" * 70)
        print("✅ Todo listo para iniciar el servidor")
        print("=" * 70)
        return 0
    except ValueError as e:
        print("   ❌ Errores de validación encontrados:")
        print()
        for line in str(e).split('\n'):
            if line.strip():
                print(f"      {line}")
        print()
        print("=" * 70)
        print("❌ Corregir errores antes de iniciar el servidor")
        print("=" * 70)
        return 1

if __name__ == '__main__':
    sys.exit(check_config())
