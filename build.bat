@echo off
REM ============================================================
REM  儿童电脑使用时长控制 - 打包脚本
REM  作者：野怼怼；https://www.bd7iwd.com
REM  许可：MIT
REM ============================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================
echo   儿童电脑使用时长控制（单机版）- 打包成单个 exe
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 python，请先安装 Python 3.9+ 并勾选 "Add python.exe to PATH"
    pause & exit /b 1
)

echo [1/3] 安装 / 更新 PyInstaller ...
python -m pip install --upgrade pyinstaller
if errorlevel 1 ( echo [错误] PyInstaller 安装失败，请检查网络 & pause & exit /b 1 )

echo.
echo [2/3] 打包中（约 1-2 分钟）...
python -m PyInstaller --noconfirm --clean --onefile --noconsole ^
    --name PCTimeControlLite ^
    --icon app.ico ^
    --version-file version_info.txt ^
    --hidden-import PyQt5.sip ^
    --add-data "web\static;static" ^
    --add-data "app.ico;." ^
    main.py
if errorlevel 1 ( echo [错误] 打包失败 & pause & exit /b 1 )

echo.
echo [3/3] 完成！
echo.
echo   生成文件：%~dp0dist\PCTimeControlLite.exe
echo.
echo   用法：
echo     1. 把这个 exe 拷到孩子电脑，放到 D:\PCTimeControl\ 之类的位置
echo     2. 双击运行（不会弹窗口，只在右下角出现一个圆点图标）
echo     3. 手机连同一个 Wi-Fi，打开托盘菜单里显示的地址（如 http://192.168.1.5:8080）
echo     4. 首次打开会让你设置管理密码和解锁密码
echo.
echo   注意：第一次运行 Windows 会弹防火墙提示，必须点「允许访问」，
echo         否则手机连不上。
echo.
pause
