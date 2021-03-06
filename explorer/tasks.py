from explorer import app_settings
from explorer.models import Query
from django.core.mail import send_mail
from explorer.utils import csv_report
from datetime import date
import random
import string


if app_settings.ENABLE_TASKS:
    from celery import task
    from celery.utils.log import get_task_logger
    import tinys3
    logger = get_task_logger(__name__)
else:
    from explorer.utils import noop_decorator as task
    import logging
    logger = logging.getLogger(__name__)


@task
def execute_query(query_id, email_address):
    q = Query.objects.get(pk=query_id)
    r = csv_report(q)
    random_part = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(20))
    resp = _upload('%s.csv' % random_part, r)

    subj = '[SQL Explorer] Report "%s" is ready' % q.title
    msg = 'Download results:\n\r%s' % resp.url

    send_mail(subj, msg, app_settings.FROM_EMAIL, [email_address])


@task
def snapshot_query(query_id):
    logger.info("Starting snapshot for query %s..." % query_id)
    q = Query.objects.get(pk=query_id)
    r = csv_report(q)
    k = 'query-%s.snap-%s.csv' % (q.id, date.today().strftime('%Y%m%d-%H:%M:%S'))
    logger.info("Uploading snapshot for query %s as %s..." % (query_id, k))
    resp = _upload(k, r)
    logger.info("Done uploading snapshot for query %s. URL: %s" % (query_id, resp.url))


def _upload(key, data):
    conn = tinys3.Connection(app_settings.S3_ACCESS_KEY,
                             app_settings.S3_SECRET_KEY,
                             default_bucket=app_settings.S3_BUCKET)
    return conn.upload(key, data)


@task
def snapshot_queries():
    logger.info("Starting query snapshots...")
    qs = Query.objects.filter(snapshot=True).values_list('id', flat=True)
    logger.info("Found %s queries to snapshot. Creating snapshot tasks..." % len(qs))
    for qid in qs:
        snapshot_query.delay(qid)
    logger.info("Done creating tasks.")
