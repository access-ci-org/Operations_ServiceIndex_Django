FROM python:3.10 AS base

#RUN wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -
#RUN echo "deb https://apt.postgresql.org/pub/repos/apt/ bullseye-pgdg main" | tee  /etc/apt/sources.list.d/pgdg.list
#RUN apt-get update -qq && apt-get install -y postgresql-client-14

# Setup env
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONFAULTHANDLER 1
ENV APP_HOME /soft/ops-registry-1.0
ENV APP_CONFIG $APP_HOME/conf/Operations_Registry_Django.conf

COPY Operations_Registry_Django/ $APP_HOME/PROD
COPY provision/web/Operations_Registry_Django.conf $APP_CONFIG

FROM base AS python-deps
RUN pip install --upgrade pip
RUN pip install pipenv
COPY provision/web/Pipfile .
COPY provision/web/Pipfile.lock .
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

FROM base AS runtime
# Copy virtual env from python-deps stage
COPY --from=python-deps /.venv /.venv
ENV PATH="/.venv/bin:$PATH"

# Logging, needed for collectstatic and runtime
RUN mkdir -p $APP_HOME/var/
# Django static content
RUN mkdir -p $APP_HOME/www/
RUN mkdir -p $APP_HOME/www/static/
RUN python $APP_HOME/PROD/manage.py collectstatic --noinput

# Create and switch to runtime user
RUN useradd --create-home appuser
# Runtime user needs to log
RUN chown -R appuser $APP_HOME/var/
# Everything else above is owned buy root and not appuser

USER appuser
WORKDIR $APP_HOME/PROD
EXPOSE 8080/tcp
