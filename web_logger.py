# -*- coding: utf-8 -*-
"""
SC-HUB External Web Logger & Bridge
Delegates asynchronous HTTP JSON logging to user_service.
"""

from __future__ import annotations
from typing import Dict, Any, Optional, Tuple
from user_service import userService, send_ticket_completed_log

__all__ = ["send_ticket_completed_log", "userService"]

