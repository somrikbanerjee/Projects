package com.somrik.expenseiq

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.somrik.expenseiq.presentation.navigation.ExpenseIQNavGraph
import com.somrik.expenseiq.ui.theme.ExpenseIQTheme
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            ExpenseIQTheme {
                ExpenseIQNavGraph()
            }
        }
    }
}
