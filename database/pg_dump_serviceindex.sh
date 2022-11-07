#!/bin/bash

DATE=`date +'%s'`
FILE=dump/serviceindex.dump.${DATE}
echo "pg_dump to: ${FILE}"

pg_dump -a -p 5434 -U serviceindex_django \
    -t serviceindex.availability -t serviceindex.site -t serviceindex.staff -t serviceindex.support \
    -t serviceindex.service -t serviceindex.host -t serviceindex.link -t serviceindex.logentry \
    -t serviceindex.event -t serviceindex.hosteventlog -t serviceindex.hosteventstatus \
    serviceindex1 >${FILE}

echo "Manually execute:"
echo "DROP OWNED BY serviceindex_django;"
echo "CREATE SCHEMA serviceindex AUTHORIZATION serviceindec_django;"
