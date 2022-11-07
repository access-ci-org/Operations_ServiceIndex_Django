#!/bin/bash

DATE=`date +'%s'`
FILE=$1
if [[ ! -r ${FILE} ]]; then
    echo "File not readable: ${FILE}"
    exit 1
fi
echo "restore dump: ${FILE}"

psql -p 5434 -U serviceindex_django serviceindex1 <${FILE}
