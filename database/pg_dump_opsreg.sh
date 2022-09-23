#!/bin/bash

DATE=`date +'%s'`
FILE=opsreg.dump.${DATE}
echo "pg_dump to: ${FILE}"

pg_dump -a -p 5434 -U opsreg_django \
    -t opsreg.availability -t opsreg.site -t opsreg.staff -t opsreg.support \
    -t opsreg.service -t opsreg.host -t opsreg.link -t opsreg.logentry \
    -t opsreg.event -t opsreg.hosteventlog -t opsreg.hosteventstatus \
    opsregistry1 >${FILE}

echo "Execute:"
echo "DROP OWNED BY opsreg_django;"
echo "CREATE SCHEMA opsreg AUTHORIZATION opsreg_django;"
