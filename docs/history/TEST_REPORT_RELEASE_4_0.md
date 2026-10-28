# Astra Studio Release 4.0 — Test Report

Дата: 2026-09-24

## Автоматическая проверка

- Python compile gate: `main.py` и изменённые модули компилируются без синтаксических ошибок.
- Полный Qt/offscreen gate без нативных caption-тестов: `296 passed, 2 skipped, 88 subtests passed`.
- Нативный Windows window gate: `2 passed`.
- Итог: `298 passed, 2 skipped, 88 subtests passed`, падений нет.
- Release 4.0 regression suite проверяет миграцию внутренней рабочей папки, фильтр дерева, свободное изменение ширины панели, запрет автоматического скрытия и жизненный цикл кнопки Run/Stop.
- Дополнительно исправлена гонка завершения LSP-процесса, выявленная полным прогоном.

## Production smoke

- PyInstaller завершил сборку `dist/Astra Studio/Astra Studio.exe` без ошибки.
- Production EXE запущен; процесс отвечал, заголовок `Astra Studio — Release 4.0` подтверждён.
- После запуска реальная внутренняя рабочая папка содержит примеры шести поддерживаемых языков и нейтральные конфиги.
- Семь прежних языковых примеров перенесены в `%LOCALAPPDATA%\AstralStudio\legacy_workspace_backup` и доступны для восстановления.

## Ограничение SmartScreen

Предупреждение «Неизвестный издатель» останется до подписания EXE доверенным сертификатом code signing. Это не исправляется изменением Python-кода.
