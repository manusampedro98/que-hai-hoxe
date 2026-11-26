import argparse
import json
from pathlib import Path
from app.config import ROOT
from app.db.repository import init_db
from app.importers.manual import read_manual
from app.importers.pipeline import import_candidates, record_failure


def main(argv=None):
    parser=argparse.ArgumentParser(description='Que Hai Hoxe? · Herramienta local del propietario')
    parser.add_argument('--db',type=Path,default=ROOT/'data'/'catalog.sqlite3',help='Base local; nunca aceptada por HTTP')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('init-db',help='Crear BD; rechaza sobrescribir')
    manual=sub.add_parser('import-json',help='Importar JSON local schema_version=1 sin descargar URLs')
    manual.add_argument('--file',required=True,type=Path)
    manual.add_argument('--dry-run',action='store_true')
    axenda=sub.add_parser('import-axenda',help='Importar la ventana oficial de 90 días, manualmente')
    axenda.add_argument('--dry-run',action='store_true')
    args=parser.parse_args(argv)
    source='manual' if args.command=='import-json' else 'axenda'
    try:
        if args.command=='init-db':
            init_db(args.db)
            print('Base creada. Ningún servidor iniciado.')
            return 0
        if not args.db.is_file():raise ValueError('Inicializa primero con init-db')
        if args.command=='import-json':
            candidates,rejected=read_manual(args.file)
        else:
            from app.importers.axenda import fetch_axenda
            candidates,rejected=fetch_axenda()
        if not candidates:
            if rejected:raise ValueError('Lote sin registros válidos; se conserva el catálogo')
        summary=import_candidates(args.db,candidates,rejected,source,dry_run=args.dry_run)
        print(json.dumps(summary,ensure_ascii=False,indent=2))
        return 0
    except (Exception,KeyboardInterrupt) as exc:
        failure_log_unavailable = False
        if args.command!='init-db' and not args.dry_run and args.db.is_file() and not getattr(exc,'failure_recorded',False):
            try:record_failure(args.db,source,type(exc).__name__)
            except Exception:
                failure_log_unavailable = True
        # Exception values may contain paths, URLs or payloads. Only safe classes are displayed.
        message = 'Operación no aplicada. Comprueba el archivo, esquema o disponibilidad de la fuente. El catálogo anterior se conserva.'
        if failure_log_unavailable:
            message += ' No se pudo registrar la incidencia en la base local.'
        print(json.dumps({'error':type(exc).__name__,'message':message},ensure_ascii=False))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
