package com.somrik.expenseiq.di;

import com.somrik.expenseiq.data.db.AppDatabase;
import com.somrik.expenseiq.data.db.dao.CategoryDao;
import dagger.internal.DaggerGenerated;
import dagger.internal.Factory;
import dagger.internal.Preconditions;
import dagger.internal.QualifierMetadata;
import dagger.internal.ScopeMetadata;
import javax.annotation.processing.Generated;
import javax.inject.Provider;

@ScopeMetadata
@QualifierMetadata
@DaggerGenerated
@Generated(
    value = "dagger.internal.codegen.ComponentProcessor",
    comments = "https://dagger.dev"
)
@SuppressWarnings({
    "unchecked",
    "rawtypes",
    "KotlinInternal",
    "KotlinInternalInJava",
    "cast"
})
public final class DatabaseModule_ProvideCategoryDaoFactory implements Factory<CategoryDao> {
  private final Provider<AppDatabase> dbProvider;

  public DatabaseModule_ProvideCategoryDaoFactory(Provider<AppDatabase> dbProvider) {
    this.dbProvider = dbProvider;
  }

  @Override
  public CategoryDao get() {
    return provideCategoryDao(dbProvider.get());
  }

  public static DatabaseModule_ProvideCategoryDaoFactory create(Provider<AppDatabase> dbProvider) {
    return new DatabaseModule_ProvideCategoryDaoFactory(dbProvider);
  }

  public static CategoryDao provideCategoryDao(AppDatabase db) {
    return Preconditions.checkNotNullFromProvides(DatabaseModule.INSTANCE.provideCategoryDao(db));
  }
}
