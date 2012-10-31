try:
    VERSION = __import__('pkg_resources') \
        .get_distribution('sentry-subscriptions').version
except Exception, e:
    VERSION = 'unknown'
