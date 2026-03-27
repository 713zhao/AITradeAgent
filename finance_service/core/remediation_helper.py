"""
Simple Remediation Helper for Auto-Fixes

Provides safe, reversible remediation strategies for common issues.
Designed for quick integration into HealthAgent.
"""

import asyncio
import subprocess
import logging
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class RemediationStatus:
    """Remediation result"""
    def __init__(self, success: bool, action: str, reason: str, execution_time_ms: float = 0):
        self.success = success
        self.action = action
        self.reason = reason
        self.execution_time_ms = execution_time_ms
        self.timestamp = datetime.now()
    
    def __repr__(self):
        return f"RemediationStatus(success={self.success}, action={self.action}, reason={self.reason})"


class RemediationHelper:
    """
    Lightweight remediation engine for common issues.
    Focuses on safe, reversible fixes.
    """
    
    # Approved packages for auto-install
    APPROVED_PACKAGES = {'flask[async]', 'asgiref', 'werkzeug'}
    
    def __init__(self, config: Dict[str, Any], venv_path: str = "venv", workspace_path: str = "."):
        self.config = config
        self.venv_path = venv_path
        self.workspace_path = workspace_path
        self.fix_attempt_count = {}
        self.last_fix_time: Dict[str, datetime] = {}
        
        # Safety limits
        self.max_attempts_per_issue = 3
        self.min_retry_interval_seconds = 60
        
        logger.info("RemediationHelper initialized")
    
    async def attempt_fix(self, issue_id: str, issue_detail: str) -> RemediationStatus:
        """
        Main entry point. Attempt to fix an issue based on its characteristics.
        """
        
        # Safety check: Rate limiting
        if self._should_skip_due_to_rate_limit(issue_id):
            logger.warning(f"Remediation skipped for {issue_id}: rate limited")
            return RemediationStatus(
                success=False,
                action="rate_limited",
                reason="Too many attempts in short time"
            )
        
        # Safety check: Max attempts
        attempt_count = self.fix_attempt_count.get(issue_id, 0)
        if attempt_count >= self.max_attempts_per_issue:
            logger.error(f"Remediation abandoned for {issue_id}: max attempts exceeded")
            return RemediationStatus(
                success=False,
                action="max_attempts_exceeded",
                reason=f"Exceeded max attempts ({self.max_attempts_per_issue})"
            )
        
        # Route to appropriate fix
        if 'flask' in issue_detail.lower() and 'async' in issue_detail.lower():
            result = await self._fix_flask_async()
        elif 'service' in issue_detail.lower() and 'unhealthy' in issue_detail.lower():
            result = await self._restart_service()
        elif 'portfolio' in issue_detail.lower() and ('500' in issue_detail or 'error' in issue_detail.lower()):
            result = await self._restart_service()
        else:
            logger.warning(f"No remediation strategy for: {issue_id}")
            return RemediationStatus(
                success=False,
                action="no_strategy",
                reason="No matching remediation strategy"
            )
        
        # Track attempt
        self.fix_attempt_count[issue_id] = attempt_count + 1
        if result.success:
            self.last_fix_time[issue_id] = datetime.now()
            logger.info(f"Remediation SUCCESS for {issue_id}: {result.reason}")
        else:
            logger.warning(f"Remediation FAILED for {issue_id}: {result.reason}")
        
        return result
    
    async def _fix_flask_async(self) -> RemediationStatus:
        """Install missing flask[async] dependency and restart service"""
        start_time = datetime.now()
        
        try:
            logger.info("Remediation: Attempting to install flask[async]")
            
            # Install dependency
            pip_cmd = f"{self.venv_path}/bin/pip install 'flask[async]' -q"
            result = await self._run_command(pip_cmd, timeout=60)
            
            if result.returncode != 0:
                return RemediationStatus(
                    success=False,
                    action="dependency_install",
                    reason=f"Installation failed: {result.stderr.decode()[:100]}"
                )
            
            # Verify import
            verify_cmd = f"{self.venv_path}/bin/python -c 'import asgiref; print(\"OK\")'"
            result = await self._run_command(verify_cmd, timeout=10)
            
            if result.returncode != 0:
                return RemediationStatus(
                    success=False,
                    action="dependency_verify",
                    reason="Dependency verification failed"
                )
            
            logger.info("Remediation: flask[async] installed, restarting service")
            
            # Restart service
            restart_result = await self._restart_service()
            
            if restart_result.success:
                elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
                return RemediationStatus(
                    success=True,
                    action="dependency_install_and_restart",
                    reason="Successfully installed flask[async] and restarted service",
                    execution_time_ms=elapsed_ms
                )
            else:
                return RemediationStatus(
                    success=False,
                    action="dependency_install_and_restart",
                    reason=f"Dependency installed but restart failed: {restart_result.reason}"
                )
            
        except Exception as e:
            logger.exception("Remediation failed for flask[async]")
            return RemediationStatus(
                success=False,
                action="dependency_install",
                reason=f"Exception: {str(e)}"
            )
    
    async def _restart_service(self) -> RemediationStatus:
        """Gracefully restart the finance service"""
        start_time = datetime.now()
        
        try:
            logger.info("Remediation: Stopping finance service")
            
            # Kill existing process
            kill_cmd = "pkill -TERM -f 'run_finance_service.py'"
            await self._run_command(kill_cmd, timeout=10)
            
            # Wait for graceful shutdown
            await asyncio.sleep(2)
            
            # Force kill if still running
            pgrep_cmd = "pgrep -f 'run_finance_service.py'"
            result = await self._run_command(pgrep_cmd, timeout=5)
            
            if result.returncode == 0:
                logger.warning("Remediation: Service still running, force kill")
                kill_cmd = "pkill -KILL -f 'run_finance_service.py'"
                await self._run_command(kill_cmd, timeout=5)
                await asyncio.sleep(1)
            
            # Start service
            logger.info("Remediation: Starting finance service")
            start_cmd = (
                f"cd {self.workspace_path} && "
                f"nohup {self.venv_path}/bin/python run_finance_service.py "
                f"> finance.log 2>&1 &"
            )
            await self._run_command_shell(start_cmd, timeout=5)
            
            # Wait for startup
            await asyncio.sleep(3)
            
            # Health check
            logger.info("Remediation: Checking service health after restart")
            for attempt in range(5):
                try:
                    # Try to connect to health endpoint using curl
                    health_cmd = "curl -s http://localhost:8801/health -m 3"
                    result = await self._run_command(health_cmd, timeout=5)
                    
                    if result.returncode == 0 and b'"ok"' in result.stdout:
                        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
                        logger.info(f"Remediation: Service health check passed in {elapsed_ms}ms")
                        return RemediationStatus(
                            success=True,
                            action="service_restart",
                            reason=f"Service successfully restarted",
                            execution_time_ms=elapsed_ms
                        )
                except:
                    pass
                
                if attempt < 4:
                    await asyncio.sleep(1)
            
            # Health check failed
            return RemediationStatus(
                success=False,
                action="service_restart",
                reason="Service started but health check failed"
            )
            
        except Exception as e:
            logger.exception("Remediation failed for service restart")
            return RemediationStatus(
                success=False,
                action="service_restart",
                reason=f"Exception: {str(e)}"
            )
    
    def _should_skip_due_to_rate_limit(self, issue_id: str) -> bool:
        """Check if we should skip this fix due to rate limiting"""
        last_attempt = self.last_fix_time.get(issue_id)
        
        if last_attempt is None:
            return False
        
        elapsed = (datetime.now() - last_attempt).total_seconds()
        return elapsed < self.min_retry_interval_seconds
    
    async def _run_command(self, cmd: str, timeout: int) -> subprocess.CompletedProcess:
        """Run shell command asynchronously"""
        try:
            process = await asyncio.wait_for(
                asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                ),
                timeout=timeout
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr
            )
        except asyncio.TimeoutError:
            logger.warning(f"Command timeout: {cmd}")
            return subprocess.CompletedProcess(args=cmd, returncode=1, stdout=b"", stderr=b"timeout")
    
    async def _run_command_shell(self, cmd: str, timeout: int) -> subprocess.CompletedProcess:
        """Run as shell command (allows && etc)"""
        return await self._run_command(cmd, timeout)
