#!/bin/bash
ssh -i <SSH_KEY_PATH> -o StrictHostKeyChecking=no -o ConnectTimeout=10 root@<INTRANET_IP> 'pip3 install paddlepaddle paddlenlp 2>&1' >> /tmp/paddle_install.log
echo "EXIT_CODE: $?"
