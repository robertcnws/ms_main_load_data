FROM mongo-express:latest

COPY wait-for-mongo.sh /usr/local/bin/wait-for-mongo.sh
RUN chmod +x /usr/local/bin/wait-for-mongo.sh

ENTRYPOINT ["/usr/local/bin/wait-for-mongo.sh"]
