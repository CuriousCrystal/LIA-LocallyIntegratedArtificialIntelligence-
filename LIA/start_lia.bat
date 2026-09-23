@echo off
rem Launch Lia from the project root, whatever directory this was called from.
rem Keeps a console window open because she still needs the keyboard for
rem push-to-talk -- that goes away once voice activity detection lands.

cd /d "%~dp0.."
title Lia

python LIA\main.py

rem Keep the window up if she exits unexpectedly, so the error is readable.
if errorlevel 1 pause
