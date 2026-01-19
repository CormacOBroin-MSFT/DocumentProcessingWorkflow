@echo off
REM Flask Backend Setup Script for Windows
REM This script sets up the Python virtual environment and installs dependencies

echo 🚀 Setting up Flask Backend for AI Document Processing...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python 3 is not installed. Please install Python 3.9 or higher.
    exit /b 1
)

echo ✅ Python found
python --version
echo.

REM Navigate to backend directory
cd /d "%~dp0"

REM Create virtual environment
echo 📦 Creating virtual environment...
if exist "venv\" (
    echo ⚠️  Virtual environment already exists. Skipping creation.
) else (
    python -m venv venv
    echo ✅ Virtual environment created
)
echo.

REM Activate virtual environment
echo 🔌 Activating virtual environment...
call venv\Scripts\activate.bat
echo ✅ Virtual environment activated
echo.

REM Upgrade pip
echo ⬆️  Upgrading pip...
python -m pip install --upgrade pip --quiet
echo ✅ pip upgraded
echo.

REM Install dependencies
echo 📥 Installing dependencies from requirements.txt...
pip install -r requirements.txt
echo ✅ Dependencies installed
echo.

REM Check if .env exists
if exist ".env" (
    echo ✅ .env file exists
) else (
    echo ⚠️  .env file not found
    echo 📝 Creating .env from .env.example...
    copy .env.example .env
    echo ✅ .env file created
    echo.
    echo ⚠️  IMPORTANT: Edit .env file with your actual Azure credentials before running the server!
    echo.
)

REM Test imports
echo 🧪 Testing imports...
python -c "import flask; import azure.storage.blob; import azure.ai.formrecognizer; import openai; print('✅ All imports successful')"
echo.

echo ✨ Setup complete!
echo.
echo 📋 Next steps:
echo   1. Edit .env file with your Azure credentials
echo   2. Activate the virtual environment: venv\Scripts\activate
echo   3. Run the server: python run.py
echo   4. Test health endpoint: curl http://localhost:5000/health
echo.
echo 📚 Documentation:
echo   - Backend README: .\README.md
echo   - Integration Guide: ..\INTEGRATION_GUIDE.md
echo.

pause
