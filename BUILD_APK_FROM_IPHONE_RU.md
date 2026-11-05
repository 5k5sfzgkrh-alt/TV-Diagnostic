# Сборка TV Diagnostic 1.3.0 через GitHub с iPhone

## Подготовка репозитория
1. Откройте https://github.com/5k5sfzgkrh-alt/TV-Diagnostic
2. В корне репозитория загрузите содержимое этого архива (именно содержимое, без внешней папки tvsrc).
3. Сохраните структуру каталогов: `.github/workflows/android.yml`, `app/build.gradle.kts`, `app/src/main/...`, `build.gradle.kts`, `settings.gradle.kts`, `gradle.properties`.
4. Не удаляйте и не заменяйте файлы приложения другими версиями без проверки.
5. Сделайте commit в ветку `main`.

## Запуск
После commit откройте вкладку Actions и выберите `Android APK`. Workflow запускается автоматически при push в `main`; также в нём предусмотрен ручной запуск `Run workflow`.

## Получение APK
Откройте успешный запуск workflow, прокрутите страницу до Artifacts и скачайте `TV-Diagnostic-v1.3.0-debug-apk`. В ZIP будут `app-debug.apk` и `APK-SHA256.txt`.

## Важно
Пока workflow не завершился успешно и APK не проверен, приложение не готово к установке. Даже успешная сборка не заменяет тест на телевизоре. Не запускайте бэкап SYSTEM/VENDOR до проверки APK и безопасного свободного места на ТВ.
