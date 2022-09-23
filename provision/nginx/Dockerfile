FROM nginx:1.23

RUN rm /etc/nginx/conf.d/default.conf
COPY provision/nginx/nginx.conf /etc/nginx/conf.d
COPY provision/nginx/operations-app.access-ci.org.key /etc/ssl/private/
COPY provision/nginx/operations-app.access-ci.org.pub /etc/ssl/certs/
RUN chmod 444 /etc/ssl/private/operations-app.access-ci.org.key
RUN chown root /etc/ssl/private/operations-app.access-ci.org.key
RUN chmod 444 /etc/ssl/certs/operations-app.access-ci.org.pub
RUN chown root /etc/ssl/certs/operations-app.access-ci.org.pub
EXPOSE 8443
