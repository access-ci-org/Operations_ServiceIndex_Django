FROM ubuntu:22.10 AS base

ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
RUN apt-get update -qq

# nginx proxy service
RUN apt-get install -y nginx
RUN apt-get install -y openssh-server sudo
EXPOSE 22/tcp

# SSL configuration
COPY provision/certs/operations-app.access-ci.org.key /etc/ssl/private/
COPY provision/certs/operations-app.access-ci.org.pub /etc/ssl/certs/
RUN chmod 444 /etc/ssl/private/operations-app.access-ci.org.key
RUN chown root /etc/ssl/private/operations-app.access-ci.org.key
RUN chmod 444 /etc/ssl/certs/operations-app.access-ci.org.pub
RUN chown root /etc/ssl/certs/operations-app.access-ci.org.pub

# PostgreSQL client for development only
#RUN wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -
#RUN echo "deb https://apt.postgresql.org/pub/repos/apt/ bullseye-pgdg main" | tee  /etc/apt/sources.list.d/pgdg.list
#RUN apt-get update -qq && apt-get install -y postgresql-client-14

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONFAULTHANDLER 1
RUN apt install -y tzdata
RUN apt-get install -y python3.10
RUN apt-get install -y python3-pip

##########################################################################
FROM base AS python-deps
RUN pip install --upgrade pip
RUN pip install pipenv
COPY provision/web/Pipfile .
COPY provision/web/Pipfile.lock .
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

##########################################################################
FROM base AS runtime

COPY --from=python-deps /.venv /.venv
ENV PATH="/.venv/bin:$PATH"

# Configure NGINX: enabld site, base settings in conf.d/, certs
RUN rm /etc/nginx/sites-enabled/default
COPY provision/combo/nginx.serviceindex /etc/nginx/sites-available/nginx.serviceindex
RUN ln -s /etc/nginx/sites-available/nginx.serviceindex /etc/nginx/sites-enabled/
COPY provision/combo/nginx.conf /etc/nginx/conf.d/nginx.conf
EXPOSE 443/tcp

ENV APP_HOME /soft/serviceindex-1.0
COPY Operations_ServiceIndex_Django/ $APP_HOME/PROD
WORKDIR $APP_HOME/PROD
ENV APP_CONFIG $APP_HOME/conf/Operations_ServiceIndex_Django.conf
COPY provision/web/Operations_ServiceIndex_Django.conf $APP_CONFIG
COPY provision/combo/gunicorn.conf.py $APP_HOME/conf/gunicorn.conf.py

# Runtime logging, also used by collectstatic
RUN mkdir -p $APP_HOME/var/
RUN mkdir -p $APP_HOME/www/static/
RUN python $APP_HOME/PROD/manage.py collectstatic --noinput

# Create and switch to runtime user
RUN useradd --create-home appuser
# Runtime logging, change owneship of setup logs if any
RUN chown -R appuser $APP_HOME/var/

# Start services
COPY provision/combo/django /etc/init.d/django
COPY provision/combo/django.service /etc/systemd/system/django.service
RUN /usr/sbin/update-rc.d django defaults
COPY provision/combo/startup.sh $APP_HOME/sbin/startup.sh

# Everything else happens as the runtime user
#USER appuser
CMD ["/bin/bash", "/soft/serviceindex-1.0/sbin/startup.sh"]
