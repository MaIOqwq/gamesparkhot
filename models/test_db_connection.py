#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
鏁版嵁搴撹繛鎺ユ祴璇曡剼鏈?娴嬭瘯涓嶮ariaDB鏁版嵁搴撶殑杩炴帴鍔熻兘
"""

import os
import sys
import logging
import argparse
import pymysql
from datetime import datetime, timedelta

# 閰嶇疆鏃ュ織
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_db_connection(host, port, user, password, database):
    """娴嬭瘯鏁版嵁搴撹繛鎺?    
    Args:
        host: 鏁版嵁搴撲富鏈?        port: 鏁版嵁搴撶鍙?        user: 鏁版嵁搴撶敤鎴峰悕
        password: 鏁版嵁搴撳瘑鐮?        database: 鏁版嵁搴撳悕绉?        
    Returns:
        bool: 杩炴帴鏄惁鎴愬姛
    """
    logger.info(f"寮€濮嬫祴璇曟暟鎹簱杩炴帴: {host}:{port}/{database}")
    
    try:
        # 杩炴帴鏁版嵁搴?        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        
        logger.info("鏁版嵁搴撹繛鎺ユ垚鍔?)
        
        # 娴嬭瘯鏌ヨ
        with conn.cursor() as cursor:
            # 鏌ヨ琛ㄧ粨鏋?            cursor.execute("DESCRIBE standardized_data")
            columns = cursor.fetchall()
            logger.info(f"standardized_data琛ㄧ粨鏋? {len(columns)} 鍒?)
            for col in columns[:5]:  # 鍙樉绀哄墠5鍒?                logger.info(f"  {col['Field']}: {col['Type']}")
            
            # 鏌ヨ鏁版嵁閲?            cursor.execute("SELECT COUNT(*) as count FROM standardized_data")
            result = cursor.fetchone()
            logger.info(f"standardized_data琛ㄦ暟鎹噺: {result['count']} 鏉?)
            
            # 鏌ヨ鏈€鏂版暟鎹?            cursor.execute("SELECT * FROM standardized_data ORDER BY publish_time DESC LIMIT 3")
            latest_data = cursor.fetchall()
            logger.info(f"鏈€鏂?鏉℃暟鎹?")
            for i, row in enumerate(latest_data):
                logger.info(f"  鏁版嵁{i+1}: keyword={row['keyword']}, publish_time={row['publish_time']}")
        
        # 鍏抽棴杩炴帴
        conn.close()
        logger.info("鏁版嵁搴撹繛鎺ユ祴璇曞畬鎴?)
        return True
        
    except Exception as e:
        logger.error(f"鏁版嵁搴撹繛鎺ュけ璐? {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """涓诲嚱鏁?""
    parser = argparse.ArgumentParser(description="鏁版嵁搴撹繛鎺ユ祴璇曡剼鏈?)
    parser.add_argument("--db_host", default="<SERVER_IP>",
                      help="鏁版嵁搴撲富鏈?)
    parser.add_argument("--db_port", type=int, default=3306,
                      help="鏁版嵁搴撶鍙?)
    parser.add_argument("--db_user", default="spark",
                      help="鏁版嵁搴撶敤鎴峰悕")
    parser.add_argument("--db_password", default="123456",
                      help="鏁版嵁搴撳瘑鐮?)
    parser.add_argument("--db_name", default="standardized_data",
                      help="鏁版嵁搴撳悕绉?)
    
    args = parser.parse_args()
    
    logger.info("=======================================")
    logger.info("鏁版嵁搴撹繛鎺ユ祴璇曞紑濮?)
    logger.info("=======================================")
    
    success = test_db_connection(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=args.db_password,
        database=args.db_name
    )
    
    logger.info("=======================================")
    if success:
        logger.info("鏁版嵁搴撹繛鎺ユ祴璇曟垚鍔?)
    else:
        logger.info("鏁版嵁搴撹繛鎺ユ祴璇曞け璐?)
    logger.info("=======================================")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())