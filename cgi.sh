#!/bin/sh

QUERY_STRING=""
echo GATEWAY_INTERFACE $GATEWAY_INTERFACE > test.log
echo REQUEST_METHOD $REQUEST_METHOD >> test.log
echo PATH_INFO $PATH_INFO >> test.log
echo QUERY_STRING $QUERY_STRING >> test.log
./nanobot >> test.log
./nanobot

