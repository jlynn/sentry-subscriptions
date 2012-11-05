from setuptools import find_packages
from setuptools import setup

install_requires = [
    'sentry>=5.0.0',
]

setup(
    name='sentry-subscriptions',
    version='0.1.0',
    author='John Lynn',
    author_email='jlynn@hearsaycorp.com',
    package_dir={'': 'src'},
    packages=find_packages('src'),
    zip_safe=False,
    install_requires=install_requires,
    entry_points={
        'sentry.plugins': [
            'subscriptions = sentry_subscriptions.plugin:SubscriptionsPlugin'
        ]
    }
)
