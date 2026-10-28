# Astra Studio

Локальная IDE для Windows и macOS. Текущая версия: **Release 5.0**.

[Скачать Windows ZIP](https://github.com/alarongh/Astra-Studio-Releases/releases/tag/v5.0) · [Изменения 5.0](CHANGELOG.md) · [Проверка выпуска](TEST_REPORT_RELEASE_5_0.md)

## Что изменилось

- Нативные пути, сочетания Command, обнаружение инструментов и сборка `.app`/`.dmg` для macOS.
- Интерфейс для масштабирования и крупных шрифтов, сохранение размеров панелей, однотонные фоны и отдельные цвета областей.
- Общее офлайн- и LSP-автодополнение; исправления UTF-16, устаревших ответов, импортов и завершения серверов.
- Асинхронная и отменяемая проверка Python-зависимостей с учётом окружения проекта.
- Доверие к проектам перед фоновым запуском инструментов; исправления обработки путей, замены файлов и локального предпросмотра.

Включены изменения [BoyJayy](https://github.com/BoyJayy) из [PR #1](https://github.com/alarongh/Astra-Studio-Releases/pull/1). Полный список и ограничения: [CHANGELOG.md](CHANGELOG.md).

## Windows: готовое приложение

1. Скачайте `Astra_Studio_Release_5_0.zip` из выпуска и проверьте его по `SHA256SUMS.txt`.
2. Полностью распакуйте папку `Astra Studio`.
3. Запустите `Astra Studio.exe`. Рядом должна оставаться папка `_internal`.

Python для запуска готовой сборки не требуется. Для выполнения пользовательских программ нужны соответствующие интерпретаторы/компиляторы. Настройки, рабочая папка и журналы находятся в `%LOCALAPPDATA%\AstralStudio`, отдельно от приложения.

Проверка обновлений использует публичный HTTPS feed, размер архива и SHA-256. Обновление сохраняет предыдущую папку приложения для восстановления. Подробнее: [portable-запуск](PORTABLE_README.md), [публикация обновлений](UPDATE_DISTRIBUTION.md).

## Запуск из исходников

Используйте Python 3.14 и зависимости из `requirements.txt`.

На Windows запустите `install_app.bat`, затем `run_astra.bat`. Установщик создаёт локальную `.venv` и устанавливает также зависимости для тестов. `reinstall_app.bat` пересоздаёт эту `.venv`.

Для macOS используются отдельные DMG-пакеты:

| Компьютер | Пакет |
| --- | --- |
| Intel, macOS 11–14 | `x86_64-legacy-macOS11.0.dmg` |
| Intel, macOS 15 Sequoia и новее | `x86_64-standard-macOS15.0.dmg` |
| Apple Silicon, macOS 15 Sequoia и новее | `arm64-standard-macOS15.0.dmg` |

Откройте подходящий DMG и перетащите `Astra Studio.app` в `Applications`. Для запуска самой IDE отдельный Python не нужен. Для запуска пользовательского Python-кода нужен внешний Python либо окружение проекта. Установка через исходники и границы проверки: [MACOS.md](MACOS.md).

Нативные компоненты пакета проверяются по архитектуре и минимальной macOS. CI запускает установку на доступных современных macOS; физический Mac с 11.7.10 проверяется владельцем отдельно. Пакеты имеют ad-hoc подпись; без Developer ID/notarization возможен запрос macOS о неизвестном разработчике.

## Возможности

Основной интерфейс: Python, C++, Java, JavaScript, HTML и CSS. Другие языковые реализации сохранены в исходниках, но скрыты до отдельной проверки.

- Редактор с вкладками, подсветкой, автодополнением, LSP-навигацией и диагностикой.
- Запуск/остановка программ, ввод в консоли, терминал и сборка Python/C++ EXE.
- Проекты, шаблоны, поиск и замена, Quick Open, Python-окружения и Project Doctor.
- Форматирование и lint через установленные инструменты, Test Explorer, Git / Source Control.
- Локальный экспорт выбранного контекста в `PROJECT_CONTEXT.md`.
- Настраиваемое оформление, собственные изображения, шрифт и значок ярлыка.

LSP, formatters, Git и toolchains требуют отдельных внешних инструментов. Однотонные фоны заменили девять встроенных фотообоев; пользовательские изображения поддерживаются и не удаляются миграцией.

## Проверка и сборка

`run_acceptance_tests.bat` запускает тесты из `.venv`. `build_exe.bat` собирает Windows portable через актуальный `astra_studio.spec`.

```powershell
.\.venv\Scripts\python.exe -m compileall -q main.py core scripts tests
.\.venv\Scripts\python.exe -m pytest -q -rs
.\build_exe.bat
.\scripts\package_release.ps1 -Version 5.0
```

CI проверяет Windows и macOS. Результаты выпуска: [отчёт 5.0](TEST_REPORT_RELEASE_5_0.md). Полный реестр: [docs/TEST_REGISTRY.md](docs/TEST_REGISTRY.md).

История 3.x/4.0, Final Integration Gate и исходный отчёт автора PR сохранены в [docs/history](docs/history/README.md). Исторические отчёты и контрольные суммы относятся к своим выпускам.
